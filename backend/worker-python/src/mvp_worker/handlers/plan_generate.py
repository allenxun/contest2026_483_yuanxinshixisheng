"""``plan.generate``：冻结报告 + 批准能力快照 → 严格校验方案 → ready。

实现 DD §7.2 / §9.4。能力待补齐改为**合法等待态**：``waiting_inputs`` 且能力
未齐 → 返回 ``HandlerResult(defer_seconds=...)``，运行时经 ``complete_deferred``
在原 job 上重排（不消耗 attempt 预算、不产生后继任务、generation_revision 恒定）；
业务守卫（``business_tx``）复核 T06 行仍 ``waiting_inputs`` 且 revision 未变，
否则 StaleGeneration 整体回滚。大模型输出**严格白名单校验**（以冻结
``input_snapshot`` 为唯一基线），非法绝不发布 ready；只写生成字段与 N，
**永不触碰** completed_count / completed_at / progress_revision（K 账本归 C）。
generation_revision 建行后永不变更。
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
from typing import Any, Callable, Optional, TypeGuard

from sqlalchemy import Connection, Engine, text

from ..logging_setup import mlog
from ..runtime.complete import BusinessTx, StaleGeneration
from ..runtime.rows import JobRow
from . import HandlerContext, HandlerResult, JobFailed
from .dshared import weijing_mapping
from .dshared.dfence import fenced_business_tx
from .dshared.jsonschema_support import load_payload_validator, validate_payload
from .dshared.providers import ProviderConfigError
from .dshared.resolve import dconfig_for, plan_port_for

log = logging.getLogger("mvp_worker.handlers.plan_generate")

JOB_TYPE = "plan.generate"
_PAYLOAD_SCHEMA = "payload-plan-generate.json"

_DIGITS_RE = re.compile(r"^[0-9]+$")
# N2 收敛码：T06 已终态 failed 但 T12 停在同代次时，重放收敛 T12 用有界泛化码
# （不读 failure_detail：诊断列不得驱动决策）。
_PLAN_GENERATION_FAILED = "PLAN_GENERATION_FAILED"

_SELECT_PLAN = text(
    """
SELECT id, assessment_id, member_id, generation_status, input_photo_version,
       generation_revision, input_snapshot
FROM care_plans
WHERE id = CAST(:id AS uuid)
"""
)

_SELECT_PLAN_FOR_UPDATE = text(
    """
SELECT id, generation_status, generation_revision, input_photo_version
FROM care_plans
WHERE id = CAST(:id AS uuid)
FOR UPDATE
"""
)

_SELECT_REPORT = text(
    """
SELECT id, status, report_id, report_payload, report_photo_version
FROM skin_assessments
WHERE id = CAST(:id AS uuid)
"""
)

_SCAN_CAPABILITY = text(
    """
SELECT id, capabilities, capabilities -> 'parameter_ranges' AS parameter_ranges,
       latest_observation, observed_at
FROM microcrystals
WHERE capabilities ->> 'capability_id' = :capability_id
  -- 错误防护：非数字 revision（缺失/文本/对象）一律不参与比较，绝不让单行脏数据
  -- 触发 ::int 转换错误毒化整批扫描（CASE 分支 + 正则双保险，避免求值顺序差异）。
  AND capabilities ->> 'revision' ~ '^[0-9]+$'
  AND CASE WHEN capabilities ->> 'revision' ~ '^[0-9]+$'
           THEN (capabilities ->> 'revision')::int ELSE -1 END >= :revision
  AND latest_observation <> '{}'::jsonb
  AND (:stale_seconds = 0
       OR (observed_at IS NOT NULL
           AND observed_at >= CURRENT_TIMESTAMP - make_interval(secs => :stale_seconds)))
ORDER BY observed_at DESC NULLS LAST, id
LIMIT 500
"""
)

# 等待守卫（defer 的 business_tx）：锁 T06 行并复核仍 waiting_inputs 且 revision 未变。
_SELECT_PLAN_GUARD = text(
    """
SELECT generation_status, generation_revision
FROM care_plans
WHERE id = CAST(:id AS uuid)
FOR UPDATE
"""
)

_SET_GENERATING = text(
    """
UPDATE care_plans
SET generation_status = 'generating', input_snapshot = CAST(:input_snapshot AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND generation_revision = :rev
  AND generation_status = 'waiting_inputs'
"""
)

_MARK_FAILED = text(
    """
UPDATE care_plans
SET generation_status = 'failed', failure_detail = CAST(:detail AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND generation_revision = :rev
  AND generation_status IN ('waiting_inputs', 'generating')
"""
)

_UPDATE_READY = text(
    """
UPDATE care_plans
SET plan_payload = CAST(:plan_payload AS jsonb),
    plan_summary = CAST(:plan_summary AS jsonb),
    target_count = :target_count,
    generation_status = 'ready',
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND generation_revision = :rev
  AND generation_status = 'generating'
"""
)


class PlanGenerateHandler:
    name = "plan-generate"

    def __init__(self) -> None:
        self._validator = None
        self._lock = threading.Lock()

    def _get_validator(self):
        if self._validator is None:
            with self._lock:
                if self._validator is None:
                    self._validator = load_payload_validator(_PAYLOAD_SCHEMA)
        return self._validator

    def validate(self, payload: object) -> None:
        validate_payload(self._get_validator(), payload, _PAYLOAD_SCHEMA)

    def handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        """围栏包装：standalone 终态/冻结写在租约失效时返回 None（见 dshared/dfence）。"""
        try:
            return self._handle(ctx, job)
        except StaleGeneration:
            mlog(
                log, logging.DEBUG, "plan.fenced_write_stale",
                **job.log_fields(), note="lease lost; business write rolled back",
            )
            return None

    def _handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        plan_id = str(job.payload["plan_id"])
        rev = int(job.payload["generation_revision"])
        dcfg = dconfig_for(ctx)

        row = _load_plan(ctx.engine, plan_id)
        if row is None:
            raise JobFailed("PLAN_NOT_FOUND", "care plan row missing", retryable=False)

        status = row["generation_status"]
        if status == "ready":
            # 已 ready：绝不重新生成/覆盖冻结内容
            return None
        if int(row["generation_revision"]) != rev:
            # 不同代次的终态/等待态：合法作废，任务成功（保持原 no-op 语义）
            mlog(log, logging.INFO, "plan.stale_generation", **job.log_fields())
            return None
        if status == "failed":
            # N2 收敛：本代次 T06 已终态 failed（T12 可能因崩溃停同代次）→ 收敛 T12 为
            # failed。不读 failure_detail（诊断列不得驱动决策），用有界泛化码；原诊断
            # 仍持久化在 T06.failure_detail 供审计。
            mlog(
                log, logging.INFO, "plan.converged_terminal",
                **job.log_fields(), code=_PLAN_GENERATION_FAILED,
            )
            raise JobFailed(
                _PLAN_GENERATION_FAILED,
                "care plan already terminal failed; converge job",
                retryable=False,
            )

        assessment_id = str(row["assessment_id"])
        input_photo_version = row["input_photo_version"]
        report = _load_report(ctx.engine, assessment_id)

        if status == "waiting_inputs":
            if not _report_is_valid(report, input_photo_version):
                self._terminal(
                    ctx, job, plan_id, rev,
                    code="REPORT_INPUT_INVALID",
                    message="frozen report input is not publishable",
                    detail={"reason": "report not ready or photo version mismatch"},
                )
                return None  # pragma: no cover
            # live 配置仅在 waiting_inputs 能力门与冻结时刻读取（B2）
            live_baseline = dcfg.plan_capability_baseline
            capability = (
                _scan_capability(ctx.engine, live_baseline, dcfg)
                if live_baseline
                else None
            )
            if not live_baseline or capability is None:
                # 能力未齐：合法等待态 → defer（同 job 重排、退还本次 attempt、
                # generation_revision 不变）；守卫复核 T06 仍 waiting_inputs 且 rev 未变。
                return HandlerResult(
                    defer_seconds=float(dcfg.plan_wait_check_seconds),
                    business_tx=_wait_guard(plan_id, rev),
                )
            assert report is not None  # _report_is_valid 已保证
            try:
                port = plan_port_for(ctx)
            except ProviderConfigError:
                # Fix 3：计划 provider 配置错误 → 立即终态 PLAN_PROVIDER_CONFIG（fenced
                # _terminal 写 T06 failed，与 T12 failed 原子；不耗尽 attempt / 不滞留）。
                self._terminal(
                    ctx, job, plan_id, rev,
                    code="PLAN_PROVIDER_CONFIG",
                    message="plan provider configuration invalid",
                    detail={"reason": "PLAN_PROVIDER_CONFIG"},
                )
                return None  # pragma: no cover - _terminal 抛出
            snapshot = _build_input_snapshot(
                report, capability, live_baseline, dcfg, port
            )
            rules = _frozen_rules(snapshot)
            if rules is None:
                # 受控基线结构不完整（缺 ranges/regions/bounds）：不得生成
                self._terminal_snapshot_invalid(ctx, job, plan_id, rev)
                return None  # pragma: no cover
            if not _set_generating(ctx.engine, job, plan_id, rev, snapshot):
                return None  # 并发变更 → 合法作废
        elif status == "generating":
            # 重试：输入快照已冻结，一律以冻结快照为基线，绝不回落 live 配置
            snapshot = row["input_snapshot"]
            rules = _frozen_rules(snapshot)
            if rules is None:
                self._terminal_snapshot_invalid(ctx, job, plan_id, rev)
                return None  # pragma: no cover
            try:
                port = plan_port_for(ctx)
            except ProviderConfigError:
                # Fix 3：计划 provider 配置错误 → 立即终态 PLAN_PROVIDER_CONFIG（fenced
                # _terminal 写 T06 failed，与 T12 failed 原子；不耗尽 attempt / 不滞留）。
                self._terminal(
                    ctx, job, plan_id, rev,
                    code="PLAN_PROVIDER_CONFIG",
                    message="plan provider configuration invalid",
                    detail={"reason": "PLAN_PROVIDER_CONFIG"},
                )
                return None  # pragma: no cover - _terminal 抛出
        else:  # pragma: no cover - CHECK 枚举已限定
            return None

        if not _report_is_valid(report, input_photo_version):
            self._terminal(
                ctx, job, plan_id, rev,
                code="REPORT_INPUT_INVALID",
                message="frozen report input is not publishable",
                detail={"reason": "report not ready or photo version mismatch"},
            )
            return None  # pragma: no cover

        if ctx.abort_event.is_set():
            return None
        report_payload = {}
        if report is not None and isinstance(report.get("report_payload"), dict):
            report_payload = report["report_payload"]
        report_context = {
            "conclusion": report_payload.get("conclusion"),
            "metrics": report_payload.get("metrics"),
            "raw_detection": report_payload.get("raw_detection"),
        }
        try:
            candidate = port.generate(report_context, snapshot)
        except JobFailed:
            raise
        except weijing_mapping.MappingNotApproved:
            # Fix 1：适配器只抛类型化异常；此处经**既有 fenced _terminal** 落库
            # （_mark_plan_failed_tx 带 plan_id + generation_revision 守卫）。
            self._terminal(
                ctx, job, plan_id, rev,
                code="PLAN_MAPPING_NOT_APPROVED",
                message="weijing plan mapping not approved",
                detail={"reason": "PLAN_MAPPING_NOT_APPROVED"},
            )
            return None  # pragma: no cover - _terminal 抛出
        except weijing_mapping.PlanProviderConfigRequired:
            self._terminal(
                ctx, job, plan_id, rev,
                code="PLAN_PROVIDER_CONFIG",
                message="weijing assess auth/config rejected",
                detail={"reason": "PLAN_PROVIDER_CONFIG"},
            )
            return None  # pragma: no cover - _terminal 抛出
        except (
            weijing_mapping.RawDetectionContractViolation,
            weijing_mapping.ResponseContractViolation,
        ):
            self._terminal(
                ctx, job, plan_id, rev,
                code="PROVIDER_CONTRACT_VIOLATION",
                message="weijing contract violation",
                detail={"reason": "PROVIDER_CONTRACT_VIOLATION"},
            )
            return None  # pragma: no cover - _terminal 抛出
        except Exception as exc:
            self._transient_or_terminal(
                ctx, job, plan_id, rev,
                code="DEPENDENCY_UNAVAILABLE",
                message="plan provider unavailable",
                detail={"reason": type(exc).__name__},
            )
            return None  # pragma: no cover

        if ctx.abort_event.is_set():
            return None

        violations = _validate_candidate(candidate, rules)
        if violations:
            if job.attempt_count >= job.max_attempts:
                self._terminal(
                    ctx, job, plan_id, rev,
                    code="PLAN_VALIDATION_FAILED",
                    message="plan provider output failed strict validation",
                    detail={"code": "PLAN_VALIDATION_FAILED",
                            "violations": violations[:20]},
                )
            raise JobFailed(
                "PLAN_VALIDATION_FAILED",
                "plan provider output failed strict validation",
                retryable=True,
            )

        normalized = _normalize_candidate(candidate)
        return HandlerResult(
            business_tx=lambda conn: _publish_plan(
                conn,
                plan_id=plan_id,
                rev=rev,
                normalized=normalized,
                report_id=(report or {}).get("report_id"),
            )
        )

    # ------------------------------------------------------------- helpers

    def _terminal(
        self,
        ctx: HandlerContext,
        job: JobRow,
        plan_id: str,
        rev: int,
        *,
        code: str,
        message: str,
        detail: dict[str, Any],
    ) -> None:
        terminal_detail = dict(detail)
        terminal_detail.setdefault("code", code)
        terminal_detail.setdefault("retryable", False)
        # 终态业务写随 complete_failure 同一事务围栏提交（N2）：无独立预提交窗口。
        raise JobFailed(
            code, message, retryable=False,
            business_tx=_mark_plan_failed_tx(plan_id, rev, terminal_detail),
        )

    def _terminal_snapshot_invalid(
        self, ctx: HandlerContext, job: JobRow, plan_id: str, rev: int
    ) -> None:
        """冻结快照缺失/畸形（缺 ranges/regions/bounds）→ 终态，绝不回落 live 配置。"""
        mlog(
            log, logging.ERROR, "plan.snapshot_invalid",
            **job.log_fields(),
            note="frozen input_snapshot missing/malformed; no live-config fallback",
        )
        self._terminal(
            ctx, job, plan_id, rev,
            code="PLAN_SNAPSHOT_INVALID",
            message="frozen input snapshot is missing or malformed",
            detail={"reason": "input_snapshot lacks frozen capability rules"},
        )

    def _transient_or_terminal(
        self,
        ctx: HandlerContext,
        job: JobRow,
        plan_id: str,
        rev: int,
        *,
        code: str,
        message: str,
        detail: dict[str, Any],
    ) -> None:
        if job.attempt_count >= job.max_attempts:
            terminal_detail = dict(detail)
            terminal_detail.setdefault("code", code)
            terminal_detail.setdefault("retryable", False)
            raise JobFailed(
                code, message, retryable=False,
                business_tx=_mark_plan_failed_tx(plan_id, rev, terminal_detail),
            )
        raise JobFailed(code, message, retryable=True)


# ---------------------------------------------------------------- module helpers


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_plan(engine: Engine, plan_id: str) -> Optional[dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(_SELECT_PLAN, {"id": plan_id}).mappings().first()
    return dict(row) if row is not None else None


def _load_report(engine: Engine, assessment_id: str) -> Optional[dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(_SELECT_REPORT, {"id": assessment_id}).mappings().first()
    return dict(row) if row is not None else None


def _report_is_valid(report: Optional[dict[str, Any]], input_photo_version: Any) -> bool:
    if report is None:
        return False
    if report.get("status") != "report_ready":
        return False
    if report.get("report_payload") is None:
        return False
    if report.get("report_photo_version") is None:
        return False
    if input_photo_version is None:
        return False
    return int(report["report_photo_version"]) == int(input_photo_version)


def _scan_capability(
    engine: Engine, baseline: dict[str, Any], dcfg: Any
) -> Optional[dict[str, Any]]:
    """扫描有效 T04 设备能力，返回**参数包络覆盖批准基线**的行。

    应用层覆盖检查（B3，无 JOIN）：候选 ``capabilities.parameter_ranges`` 必须
    与批准基线同名参数、同单位，且 ``device.min <= baseline.min`` 且
    ``device.max >= baseline.max``；不覆盖的行不构成有效确认（继续等待）。
    """
    baseline_ranges = baseline.get("parameter_ranges", {}) or {}
    with engine.connect() as conn:
        rows = conn.execute(
            _SCAN_CAPABILITY,
            {
                "capability_id": baseline.get("capability_id"),
                "revision": int(baseline.get("revision", 0)),
                "stale_seconds": int(dcfg.plan_capability_stale_seconds),
            },
        ).mappings().all()
    for row in rows:
        candidate = dict(row)
        if _covers_baseline(candidate.get("parameter_ranges"), baseline_ranges):
            return candidate
    return None


def _covers_baseline(candidate_ranges: Any, baseline_ranges: Any) -> bool:
    """设备参数包络是否覆盖批准基线（同名参数、同单位、包络更宽或相等）。"""
    if not isinstance(candidate_ranges, dict) or not isinstance(baseline_ranges, dict):
        return False
    if not baseline_ranges:
        return False
    for name, base in baseline_ranges.items():
        if not isinstance(base, dict):
            return False
        dev = candidate_ranges.get(name)
        if not isinstance(dev, dict):
            return False
        if dev.get("unit") != base.get("unit"):
            return False
        try:
            if float(dev.get("min", 0)) > float(base.get("min", 0)):
                return False
            if float(dev.get("max", 0)) < float(base.get("max", 0)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _build_input_snapshot(
    report: dict[str, Any],
    capability: dict[str, Any],
    baseline: dict[str, Any],
    dcfg: Any,
    port: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report": {
            "assessment_id": str(report["id"]),
            "report_id": str(report["report_id"]),
            "report_photo_version": int(report["report_photo_version"]),
        },
        "capability": {
            "microcrystal_id": str(capability["id"]),
            "capability_id": baseline.get("capability_id"),
            "capability_revision": int(baseline.get("revision", 0)),
            "parameter_ranges": baseline.get("parameter_ranges", {}),
            # B1：批准区域与 N 边界在 generating 转换时一次冻结，重试只读快照
            "approved_regions": list(baseline.get("approved_regions", []) or []),
            "n_bounds": dict(baseline.get("n_bounds", {}) or {}),
        },
        "model": {
            "plan_provider": getattr(port, "provider_name", "unknown"),
            "model_version": getattr(port, "model_version", "unknown"),
            "prompt_template_version": dcfg.plan_prompt_template_version,
        },
    }


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_MAX_TEXT_LEN = 256


def _is_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> TypeGuard[float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_bounded_str(value: Any, *, max_len: int = _MAX_TEXT_LEN) -> TypeGuard[str]:
    return isinstance(value, str) and 0 < len(value) <= max_len


def _is_uuid_str(value: Any) -> bool:
    return isinstance(value, str) and _UUID_RE.match(value) is not None


def _valid_parameter_ranges(ranges: Any) -> bool:
    if not isinstance(ranges, dict) or not ranges:
        return False
    for name, entry in ranges.items():
        if not _is_bounded_str(name):
            return False
        if not isinstance(entry, dict):
            return False
        if not _is_bounded_str(entry.get("unit")):
            return False
        low, high = entry.get("min"), entry.get("max")
        if not _is_number(low) or not _is_number(high):
            return False
        if float(low) > float(high):
            return False
    return True


def _valid_approved_regions(regions: Any) -> bool:
    if not isinstance(regions, list) or not regions:
        return False
    seen: set[str] = set()
    for region in regions:
        if not _is_bounded_str(region) or region in seen:
            return False
        seen.add(region)
    return True


def _valid_n_bounds(n_bounds: Any) -> bool:
    if not isinstance(n_bounds, dict):
        return False
    low, high = n_bounds.get("min"), n_bounds.get("max")
    if not _is_int(low) or not _is_int(high):
        return False
    return low > 0 and high > 0 and low <= high


def _frozen_rules(snapshot: Any) -> Optional[dict[str, Any]]:
    """完整校验冻结 input_snapshot 契约后提取校验基线（oracle R2）。

    任一字段缺失/畸形 → None，调用方落终态 ``PLAN_SNAPSHOT_INVALID``（fenced，
    T06 failed + 内部 failure_detail + ERROR 日志），**不调用 provider、不发布
    ready、不抛未处理异常**；**绝不回落 live 配置**。

    校验：schema_version==1；report{assessment_id/report_id UUID、photo_version>0}；
    model 三字段有界非空串；capability provenance{microcrystal_id/capability_id
    非空串、capability_revision int}；parameter_ranges 非空且每项 {unit 非空串、
    min/max 有限数、min<=max}；approved_regions 非空唯一有界串；
    n_bounds{min/max 正整数、min<=max}。
    """
    if not isinstance(snapshot, dict):
        return None
    if not _is_int(snapshot.get("schema_version")) or snapshot.get("schema_version") != 1:
        return None

    report = snapshot.get("report")
    if not isinstance(report, dict):
        return None
    if not _is_uuid_str(report.get("assessment_id")) or not _is_uuid_str(
        report.get("report_id")
    ):
        return None
    photo_version = report.get("report_photo_version")
    if not _is_int(photo_version) or photo_version <= 0:
        return None

    model = snapshot.get("model")
    if not isinstance(model, dict):
        return None
    for key in ("plan_provider", "model_version", "prompt_template_version"):
        if not _is_bounded_str(model.get(key)):
            return None

    capability = snapshot.get("capability")
    if not isinstance(capability, dict):
        return None
    if not _is_bounded_str(capability.get("microcrystal_id")):
        return None
    if not _is_bounded_str(capability.get("capability_id")):
        return None
    if not _is_int(capability.get("capability_revision")):
        return None

    ranges = capability.get("parameter_ranges")
    if not _valid_parameter_ranges(ranges):
        return None
    regions = capability.get("approved_regions")
    if not _valid_approved_regions(regions):
        return None
    n_bounds = capability.get("n_bounds")
    if not _valid_n_bounds(n_bounds):
        return None

    return {
        "parameter_ranges": ranges,
        "approved_regions": regions,
        "n_bounds": n_bounds,
    }


def _wait_guard(plan_id: str, rev: int) -> Callable[[Connection], None]:
    """defer 的 business_tx：锁 T06 行并复核仍 ``waiting_inputs`` 且 revision 未变。

    不一致（含行消失）→ :class:`StaleGeneration`，complete_deferred 整体回滚
    （无 refund、无状态变更）。
    """

    def tx(conn: Connection) -> None:
        row = conn.execute(
            _SELECT_PLAN_GUARD, {"id": plan_id}
        ).mappings().first()
        if (
            row is None
            or row["generation_status"] != "waiting_inputs"
            or int(row["generation_revision"]) != rev
        ):
            raise StaleGeneration(
                f"plan {plan_id} changed since claim (revision={rev}); defer rolled back"
            )

    return tx


def _set_generating(
    engine: Engine, job: JobRow, plan_id: str, rev: int, snapshot: dict[str, Any]
) -> bool:
    with fenced_business_tx(engine, job) as conn:
        res = conn.execute(
            _SET_GENERATING,
            {"id": plan_id, "rev": rev, "input_snapshot": _json(snapshot)},
        )
        return res.rowcount > 0


def _mark_plan_failed_tx(plan_id: str, rev: int, detail: dict[str, Any]) -> BusinessTx:
    """终态业务写回调：在 ``complete_failure`` 同一事务内写 T06 failed（禁网络）。

    0 行（代次/状态已被并发推进）→ :class:`StaleGeneration`：整个完成事务回滚，
    旧代次的终态写绝不落到新一代 T06（oracle Fix 1 的 no-op 契约）。
    """

    def tx(conn: Connection) -> None:
        res = conn.execute(
            _MARK_FAILED, {"id": plan_id, "rev": rev, "detail": _json(detail)}
        )
        if res.rowcount == 0:
            raise StaleGeneration(
                f"plan {plan_id} stale generation on terminal write (revision={rev})"
            )

    return tx


def _parse_target_count(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _DIGITS_RE.match(value):
        return int(value)
    return None


def _validate_candidate(candidate: Any, rules: Optional[dict[str, Any]]) -> list[str]:
    """以**冻结快照规则**校验候选；返回 bounded json_paths 违规列表，空列表 = 通过。

    ``rules`` = ``_frozen_rules(input_snapshot)``，绝不使用 live 配置。绝不回显具体值。
    """
    violations: list[str] = []
    if rules is None:
        return ["$: frozen capability rules not available"]
    ranges = rules.get("parameter_ranges", {}) or {}
    approved_regions = set(rules.get("approved_regions", []) or [])
    n_bounds = rules.get("n_bounds", {}) or {}

    description = getattr(candidate, "description", None)
    if not isinstance(description, str) or not description.strip():
        violations.append("$.description: type violated")

    target = _parse_target_count(getattr(candidate, "target_count", None))
    if target is None or target <= 0:
        violations.append("$.target_count: type or minimum violated")
    else:
        n_min = int(n_bounds.get("min", 1))
        n_max = int(n_bounds.get("max", 0))
        if not (n_min <= target <= n_max):
            violations.append("$.target_count: out of approved range")

    steps = getattr(candidate, "steps", None)
    if not isinstance(steps, list) or not steps:
        violations.append("$.steps: minItems violated")
        return violations[:20]

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            violations.append(f"$.steps[{i}]: type violated")
            continue
        if set(step) - {"step_id", "region", "parameters"}:
            violations.append(f"$.steps[{i}]: additionalProperties violated")
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id or len(step_id) > 64:
            violations.append(f"$.steps[{i}].step_id: type violated")
        region = step.get("region")
        if region not in approved_regions:
            violations.append(f"$.steps[{i}].region: not in approved regions")
        parameters = step.get("parameters")
        if not isinstance(parameters, dict):
            violations.append(f"$.steps[{i}].parameters: type violated")
            continue
        for name, value in parameters.items():
            if name not in ranges:
                violations.append(
                    f"$.steps[{i}].parameters.{name}: not in approved ranges"
                )
                continue
            rng = ranges[name] or {}
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                violations.append(f"$.steps[{i}].parameters.{name}: type violated")
                continue
            if not (float(rng.get("min", 0)) <= float(value) <= float(rng.get("max", 0))):
                violations.append(
                    f"$.steps[{i}].parameters.{name}: out of approved range"
                )
    return violations[:20]


def _normalize_candidate(candidate: Any) -> dict[str, Any]:
    target = _parse_target_count(getattr(candidate, "target_count", None))
    steps: list[dict[str, Any]] = []
    for step in getattr(candidate, "steps", []):
        params: dict[str, Any] = {}
        for name, value in (step.get("parameters") or {}).items():
            params[name] = int(value) if isinstance(value, float) and value.is_integer() else value
        steps.append(
            {
                "step_id": str(step.get("step_id", "")),
                "region": step.get("region"),
                "parameters": params,
            }
        )
    description = str(getattr(candidate, "description", ""))
    target_value: int = target if isinstance(target, int) and not isinstance(target, bool) else 0
    return {
        "schema_version": 1,
        "description": description,
        "steps": steps,
        "target_count": target_value,
        "plan_summary_description": description[:500],
    }


def _publish_plan(
    conn: Connection,
    *,
    plan_id: str,
    rev: int,
    normalized: dict[str, Any],
    report_id: Any,
) -> None:
    locked = conn.execute(
        _SELECT_PLAN_FOR_UPDATE, {"id": plan_id}
    ).mappings().first()
    if locked is None:
        return
    if locked["generation_status"] != "generating":
        return
    if int(locked["generation_revision"]) != rev:
        return
    plan_payload = {
        "schema_version": 1,
        "description": normalized["description"],
        "steps": normalized["steps"],
    }
    plan_summary = {
        "schema_version": 1,
        "description": normalized["plan_summary_description"],
        "source_report_id": str(report_id) if report_id is not None else None,
        "target_count": str(normalized["target_count"]),
    }
    conn.execute(
        _UPDATE_READY,
        {
            "id": plan_id,
            "rev": rev,
            "plan_payload": _json(plan_payload),
            "plan_summary": _json(plan_summary),
            "target_count": normalized["target_count"],
        },
    )


handler = PlanGenerateHandler()

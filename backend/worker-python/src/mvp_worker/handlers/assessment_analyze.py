"""``assessment.analyze``：测肤分析 → 身份归档 → 报告发布 → 方案交接。

实现 DD §7.1 状态机、§9.3 身份归档、§9.4 报告发布。所有外部调用（人脸/测肤/
存储）在事务外；业务写通过 :class:`HandlerResult.business_tx` 与代次受控的任务
完成在同一事务提交。旧 processing_revision 输入 → 无写回、任务成功（合法作废）。

关键边界（与 Java M3-A03 的协调点）：``photo_versions`` 归 Java 所有，Worker
**不重写**它。补拍要求写进 Worker 自有列 ``identity_result`` + ``failure_code``
+ ``failure_detail.required_views``，由 Java 侧投影时归并。
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Connection, Engine, text

from ..logging_setup import mlog
from ..runtime.complete import StaleGeneration
from ..runtime.rows import JobRow
from . import HandlerContext, HandlerResult, JobFailed
from .dshared.constants import (
    REQUIRED_VIEWS_ALL,
    candidate_entity_id,
    enroll_correlation_id,
    namespace_owner_id,
)
from .dshared.dconfig import DConfig
from .dshared.dfence import fenced_business_tx
from .dshared.dmedia import ArchiveError, archive_result_images, load_image_bytes
from .dshared.denqueue import EnrollSlotOccupied, enqueue_identity_enroll, insert_job
from .dshared.jsonschema_support import load_payload_validator, validate_payload
from .dshared.providers import ProviderUnavailable
from .dshared.resolve import dconfig_for, face_port_for, skin_port_for, storage_for

log = logging.getLogger("mvp_worker.handlers.assessment_analyze")

JOB_TYPE = "assessment.analyze"
_PAYLOAD_SCHEMA = "payload-assessment-analyze.json"

_SELECT_ASSESSMENT = text(
    """
SELECT id, status, member_id, current_photo_version, processing_revision, photo_versions
FROM skin_assessments
WHERE id = CAST(:id AS uuid)
"""
)

_SELECT_ASSESSMENT_FOR_UPDATE = text(
    """
SELECT id, status, current_photo_version, processing_revision
FROM skin_assessments
WHERE id = CAST(:id AS uuid)
FOR UPDATE
"""
)

_MARK_ANALYZING = text(
    """
UPDATE skin_assessments
SET status = 'analyzing', updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND processing_revision = :rev
  AND status IN ('queued', 'analyzing')
"""
)

_MARK_RETAKE = text(
    """
UPDATE skin_assessments
SET status = 'needs_retake',
    identity_result = CAST(:identity_result AS jsonb),
    failure_code = :failure_code,
    failure_detail = CAST(:failure_detail AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND processing_revision = :rev
  AND status IN ('queued', 'analyzing')
"""
)

_PERSIST_ENROLL_PENDING = text(
    """
UPDATE skin_assessments
SET status = 'analyzing', identity_result = CAST(:identity_result AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND processing_revision = :rev
  AND status IN ('queued', 'analyzing')
"""
)

_MARK_FAILED = text(
    """
UPDATE skin_assessments
SET status = 'failed', failure_code = :code,
    failure_detail = CAST(:detail AS jsonb), updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND processing_revision = :rev
  AND status IN ('queued', 'analyzing')
"""
)

_SELECT_MEMBER_BY_REF = text(
    "SELECT id FROM members WHERE identity_namespace = :ns AND face_subject_ref = :ref"
)

_UPDATE_PUBLISH = text(
    """
UPDATE skin_assessments
SET member_id = CAST(:member_id AS uuid),
    status = 'report_ready',
    report_id = CAST(:report_id AS uuid),
    report_summary = CAST(:report_summary AS jsonb),
    report_payload = CAST(:report_payload AS jsonb),
    report_photo_version = :report_photo_version,
    report_ready_at = CURRENT_TIMESTAMP,
    identity_result = CAST(:identity_result AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND processing_revision = :rev AND status = 'analyzing'
"""
)

_INSERT_PLAN = text(
    """
INSERT INTO care_plans (id, assessment_id, member_id, generation_status,
                        input_photo_version, generation_revision, input_snapshot,
                        plan_summary, target_count, completed_count, progress_revision,
                        created_at, updated_at)
VALUES (CAST(:id AS uuid), CAST(:assessment_id AS uuid), CAST(:member_id AS uuid),
        'waiting_inputs', :input_photo_version, 0, '{}'::jsonb,
        CAST(:plan_summary AS jsonb), NULL, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (assessment_id) DO NOTHING
RETURNING id
"""
)

_SELECT_PLAN_ID = text(
    "SELECT id FROM care_plans WHERE assessment_id = CAST(:assessment_id AS uuid)"
)


class _ContractViolation(RuntimeError):
    """测肤结果违反受控基线（消息只含 json_path，不含值）。"""


def _bounded_views(views: Any) -> list[str]:
    if not isinstance(views, (list, tuple)):
        return list(REQUIRED_VIEWS_ALL)
    ordered = [v for v in REQUIRED_VIEWS_ALL if v in set(views)]
    return ordered or list(REQUIRED_VIEWS_ALL)


class AssessmentAnalyzeHandler:
    name = "assessment-analyze"

    def __init__(self) -> None:
        self._validator = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------- contract

    def _get_validator(self):
        if self._validator is None:
            with self._lock:
                if self._validator is None:
                    self._validator = load_payload_validator(_PAYLOAD_SCHEMA)
        return self._validator

    def validate(self, payload: object) -> None:
        validate_payload(self._get_validator(), payload, _PAYLOAD_SCHEMA)

    # ------------------------------------------------------------- handle

    def handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        """围栏包装：standalone 业务写在租约失效时抛 StaleGeneration → 返回 None。

        见 ``dshared/dfence`` 与 ``runtime/loop.py``：返回 None 走
        ``complete_success`` 围栏丢弃，只留单条 ``job.complete_stale_generation``，
        不误报为未处理异常，也不产生 spurious 终态。
        """
        try:
            return self._handle(ctx, job)
        except StaleGeneration:
            mlog(
                log, logging.WARNING, "analyze.fenced_write_stale",
                **job.log_fields(), note="lease lost; business write rolled back",
            )
            return None

    def _handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        assessment_id = str(job.payload["assessment_id"])
        rev = int(job.payload["processing_revision"])
        dcfg = dconfig_for(ctx)

        row = _load_assessment(ctx.engine, assessment_id)
        if row is None:
            raise JobFailed("ASSESSMENT_NOT_FOUND", "assessment row missing", retryable=False)
        if int(row["processing_revision"]) != rev:
            # 旧输入代次：合法作废，无写回，任务成功。
            mlog(log, logging.INFO, "analyze.stale_input", **job.log_fields())
            return None

        current_photo_version = int(row["current_photo_version"])
        media_ids = _images_for_version(row["photo_versions"], current_photo_version)
        if media_ids is None:
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="SOURCE_IMAGE_UNAVAILABLE",
                message="current photo version images unavailable",
                reason="photo_versions has no entry for current_photo_version",
            )
            return None  # pragma: no cover - helper always raises

        images = load_image_bytes(ctx.engine, storage_for(ctx), media_ids)
        if isinstance(images, str):
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="SOURCE_IMAGE_UNAVAILABLE",
                message="source image object unavailable",
                reason=images,
            )
            return None  # pragma: no cover

        face = face_port_for(ctx)
        skin = skin_port_for(ctx)
        storage = storage_for(ctx)

        # 2) 标记 analyzing（自有短事务；0 行 = 并发变更 → 合法作废）
        if not _mark_analyzing(ctx.engine, job, assessment_id, rev):
            mlog(log, logging.INFO, "analyze.mark_analyzing_noop", **job.log_fields())
            return None

        # 3) 质量 + 同人
        if ctx.abort_event.is_set():
            return None
        try:
            quality = face.quality(images)
        except ProviderUnavailable:
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="DEPENDENCY_UNAVAILABLE", message="face quality unavailable",
                reason="quality provider unavailable",
            )
            return None  # pragma: no cover
        if getattr(quality, "status", "accepted") != "accepted":
            views = _bounded_views(getattr(quality, "required_views", ()))
            return self._retake_result(
                ctx, job, assessment_id, rev,
                classification="quality_rejected", code="QUALITY_REJECTED",
                required_views=views, detail="quality check rejected current views",
            )
        if ctx.abort_event.is_set():
            return None
        try:
            same = face.same_person(images)
        except ProviderUnavailable:
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="DEPENDENCY_UNAVAILABLE", message="same-person check unavailable",
                reason="same_person provider unavailable",
            )
            return None  # pragma: no cover
        if not getattr(same, "ok", False):
            return self._retake_result(
                ctx, job, assessment_id, rev,
                classification="not_same_person", code="NOT_SAME_PERSON",
                required_views=list(REQUIRED_VIEWS_ALL),
                detail="three views are not the same person",
            )

        # 4) 测肤分析 + 白名单校验
        if ctx.abort_event.is_set():
            return None
        try:
            analysis = skin.analyze(images)
            metrics = _validate_metrics(dcfg, analysis.metrics)
        except _ContractViolation as exc:
            self._terminal(
                ctx, job, assessment_id, rev,
                code="PROVIDER_CONTRACT_VIOLATION",
                message="skin provider contract violation",
                reason=str(exc)[:200],
            )
            return None  # pragma: no cover
        except JobFailed:
            raise
        except Exception as exc:
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="DEPENDENCY_UNAVAILABLE",
                message="skin provider unavailable",
                reason=type(exc).__name__,
            )
            return None  # pragma: no cover

        # 5) 结果图归档（发布前完成；幂等复用 provider_ref）
        if ctx.abort_event.is_set():
            return None
        try:
            archived = archive_result_images(
                ctx.engine, storage,
                environment=ctx.config.environment,
                assessment_id=assessment_id,
                photo_version=current_photo_version,
                result_images=getattr(analysis, "result_images", []) or [],
                max_bytes=dcfg.result_image_max_bytes,
            )
        except ArchiveError as exc:
            if exc.terminal:
                self._terminal(
                    ctx, job, assessment_id, rev,
                    code=exc.code, message="result image archive failed",
                    reason=exc.message,
                )
            else:
                self._transient_or_terminal(
                    ctx, job, assessment_id, rev,
                    code=exc.code, message="result image archive failed",
                    reason=exc.message,
                )
            return None  # pragma: no cover

        # 6) 身份 1:N 检索
        if ctx.abort_event.is_set():
            return None
        try:
            search = face.search_1n(dcfg.identity_namespace, images)
        except ProviderUnavailable:
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="DEPENDENCY_UNAVAILABLE", message="face search unavailable",
                reason="search provider unavailable",
            )
            return None  # pragma: no cover
        classification = getattr(search, "classification", "ambiguous")

        if classification == "dependency_failed":
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="DEPENDENCY_UNAVAILABLE", message="face search unavailable",
                reason="search dependency_failed",
            )
            return None  # pragma: no cover

        if classification in ("uncertain", "ambiguous"):
            return self._retake_result(
                ctx, job, assessment_id, rev,
                classification="uncertain", code="IDENTITY_UNCERTAIN",
                required_views=list(REQUIRED_VIEWS_ALL),
                detail="identity result uncertain; re-capture required",
            )

        if classification == "reliable_new":
            # 先对账 PG：本候选的登记此前是否已成功。登记协调横跨独立 job/进程，
            # 供应商替身/索引的可见性状态不保证跨调用保留；且 PG 成员行是权威事实。
            # 已存在成员 → 直接发布（重试不重复建正式成员），不再入队第二次登记。
            candidate_id = candidate_entity_id(dcfg.identity_namespace, assessment_id)
            reconciled_member_id = _find_member(
                ctx.engine, dcfg.identity_namespace, candidate_id
            )
            if reconciled_member_id is None:
                return self._handle_reliable_new(
                    ctx, job, dcfg, assessment_id, rev, current_photo_version, media_ids
                )
            member_id = reconciled_member_id
            identity_result = {
                "schema_version": 1,
                "classification": "reliable_new",
                "quality": {"status": "accepted", "required_views": []},
                "phase": "enrolled_reconciled",
                "candidate_entity_id": candidate_id,
                "member_id": member_id,
            }
        elif classification == "matched":
            # MATCHED → 解析成员（provider 可见性延迟 → 可重试至预算）
            face_subject_ref = getattr(search, "face_subject_ref", None)
            member_id = _find_member(ctx.engine, dcfg.identity_namespace, face_subject_ref)
            if member_id is None:
                self._transient_or_terminal(
                    ctx, job, assessment_id, rev,
                    code="MEMBER_NOT_VISIBLE", message="matched member not yet visible",
                    reason="member row missing for matched face_subject_ref",
                )
                return None  # pragma: no cover
            identity_result = {
                "schema_version": 1,
                "classification": "matched",
                "quality": {"status": "accepted", "required_views": []},
                "member_id": member_id,
            }
        else:
            self._transient_or_terminal(
                ctx, job, assessment_id, rev,
                code="DEPENDENCY_UNAVAILABLE", message="unexpected identity classification",
                reason="unexpected classification",
            )
            return None  # pragma: no cover

        # 7) 发布
        report_id = str(uuid.uuid4())
        report_summary = {
            "schema_version": 1,
            "conclusion": analysis.conclusion,
            "headline_metrics": [m["name"] for m in metrics][:8],
        }
        report_payload = {
            "schema_version": 1,
            "conclusion": analysis.conclusion,
            "metrics": metrics,
            "description": analysis.description,
            "images": [
                {"media_id": img["media_id"], "caption": img["caption"]} for img in archived
            ],
            "model_info": {
                "skin_provider": getattr(skin, "provider_name", "unknown"),
                "model_version": getattr(analysis, "model_version", "unknown"),
            },
        }
        return HandlerResult(
            business_tx=lambda conn: _publish(
                conn,
                assessment_id=assessment_id,
                rev=rev,
                member_id=member_id,
                report_id=report_id,
                report_summary=report_summary,
                report_payload=report_payload,
                identity_result=identity_result,
                max_attempts=ctx.config.retry_max_attempts,
            )
        )

    # ------------------------------------------------------------- helpers

    def _handle_reliable_new(
        self,
        ctx: HandlerContext,
        job: JobRow,
        dcfg: DConfig,
        assessment_id: str,
        rev: int,
        current_photo_version: int,
        media_ids: dict[str, str],
    ) -> Optional[HandlerResult]:
        ns = dcfg.identity_namespace
        candidate_id = candidate_entity_id(ns, assessment_id)
        correlation_id = enroll_correlation_id(ns, assessment_id)

        # 先持久化阶段（自有短事务、代次守卫），再做跨事务入队
        identity_result = {
            "schema_version": 1,
            "classification": "reliable_new",
            "candidate_entity_id": candidate_id,
            "phase": "enroll_pending",
            "correlation_id": correlation_id,
        }
        if not _persist_enroll_pending(ctx.engine, job, assessment_id, rev, identity_result):
            mlog(log, logging.INFO, "analyze.enroll_persist_noop", **job.log_fields())
            return None

        payload = {
            "schema_version": 1,
            "correlation_id": correlation_id,
            "assessment_id": assessment_id,
            "photo_version": str(current_photo_version),
            "processing_revision": str(rev),
            "images": {
                "front": media_ids["front"],
                "left": media_ids["left"],
                "right": media_ids["right"],
            },
            "provider_config_revision": dcfg.provider_config_revision,
        }
        try:
            enqueue_identity_enroll(
                ctx.engine,
                job_type="identity.enroll",
                dedup_key=f"identity:{ns}:{candidate_id}",
                owner_type="identity_namespace",
                owner_id=namespace_owner_id(ns),
                input_revision=rev,
                payload=payload,
                max_attempts=ctx.config.retry_max_attempts,
            )
        except EnrollSlotOccupied:
            # namespace 未决登记占满：本候选等待重搜（绝不并行登记第二份）
            pass

        # 无论新入队/重放/槽占用，本次分析都不能发布：等待登记完成后重搜命中。
        if job.attempt_count >= job.max_attempts:
            # 预算耗尽：登记协调项仍在（槽位保持占用），本任务落 failed 终态。
            _mark_failed(
                ctx.engine, job, assessment_id, rev, "IDENTITY_ENROLLMENT_TIMEOUT",
                "enrollment did not complete within attempt budget",
            )
            raise JobFailed(
                "IDENTITY_ENROLLMENT_TIMEOUT",
                "reliable new candidate enrollment timed out",
                retryable=False,
            )
        raise JobFailed(
            "IDENTITY_ENROLLMENT_PENDING",
            "reliable new candidate awaiting enrollment",
            retryable=True,
        )

    def _retake_result(
        self,
        ctx: HandlerContext,
        job: JobRow,
        assessment_id: str,
        rev: int,
        *,
        classification: str,
        code: str,
        required_views: list[str],
        detail: str,
    ) -> HandlerResult:
        views = _bounded_views(required_views)
        identity_result = {
            "schema_version": 1,
            "classification": classification,
            "quality": {"status": "needs_retake", "required_views": views},
            "detail": detail[:200],
        }
        # failure_detail 仅内部诊断（裁定 3）：required_views 唯一权威通道 = identity_result.quality
        failure_detail = {"reason": detail[:200]}

        def tx(conn: Connection) -> None:
            conn.execute(
                _MARK_RETAKE,
                {
                    "id": assessment_id,
                    "rev": rev,
                    "identity_result": _json(identity_result),
                    "failure_code": code,
                    "failure_detail": _json(failure_detail),
                },
            )

        return HandlerResult(business_tx=tx)

    def _terminal(
        self,
        ctx: HandlerContext,
        job: JobRow,
        assessment_id: str,
        rev: int,
        *,
        code: str,
        message: str,
        reason: str,
    ) -> None:
        _mark_failed(ctx.engine, job, assessment_id, rev, code, reason)
        raise JobFailed(code, message, retryable=False)

    def _transient_or_terminal(
        self,
        ctx: HandlerContext,
        job: JobRow,
        assessment_id: str,
        rev: int,
        *,
        code: str,
        message: str,
        reason: str,
    ) -> None:
        if job.attempt_count >= job.max_attempts:
            _mark_failed(ctx.engine, job, assessment_id, rev, code, reason)
            raise JobFailed(code, message, retryable=False)
        raise JobFailed(code, message, retryable=True)


# ---------------------------------------------------------------- module helpers


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_assessment(engine: Engine, assessment_id: str) -> Optional[dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(_SELECT_ASSESSMENT, {"id": assessment_id}).mappings().first()
    return dict(row) if row is not None else None


def _images_for_version(photo_versions: Any, current_photo_version: int) -> Optional[dict[str, str]]:
    if not isinstance(photo_versions, dict):
        return None
    for entry in photo_versions.get("versions", []) or []:
        if not isinstance(entry, dict):
            continue
        if int(entry.get("version", -1)) == current_photo_version:
            images = entry.get("images")
            if isinstance(images, dict) and all(
                isinstance(images.get(v), str) for v in REQUIRED_VIEWS_ALL
            ):
                return {
                    "front": images["front"],
                    "left": images["left"],
                    "right": images["right"],
                }
    return None


def _validate_metrics(dcfg: DConfig, raw: Any) -> list[dict[str, Any]]:
    baseline = dcfg.metric_baseline_by_name()
    if not baseline:
        raise _ContractViolation("$.metrics baseline not configured")
    if not isinstance(raw, list) or not raw:
        raise _ContractViolation("$.metrics: expected non-empty array")
    normalized: list[dict[str, Any]] = []
    allowed = {"name", "value", "unit"}
    for i, metric in enumerate(raw):
        if not isinstance(metric, dict):
            raise _ContractViolation(f"$.metrics[{i}]: type violated")
        if set(metric) - allowed:
            raise _ContractViolation(f"$.metrics[{i}]: additionalProperties violated")
        name = metric.get("name")
        unit = metric.get("unit")
        value = metric.get("value")
        if not isinstance(name, str) or name not in baseline:
            raise _ContractViolation(f"$.metrics[{i}].name: not in approved baseline")
        base = baseline[name]
        if unit != base.get("unit"):
            raise _ContractViolation(f"$.metrics[{i}].unit: not in approved baseline")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise _ContractViolation(f"$.metrics[{i}].value: type violated")
        if not (float(base["min"]) <= float(value) <= float(base["max"])):
            raise _ContractViolation(f"$.metrics[{i}].value: out of approved range")
        normalized.append({"name": name, "value": value, "unit": unit})
    return normalized


def _mark_analyzing(engine: Engine, job: JobRow, assessment_id: str, rev: int) -> bool:
    with fenced_business_tx(engine, job) as conn:
        res = conn.execute(_MARK_ANALYZING, {"id": assessment_id, "rev": rev})
        return res.rowcount > 0


def _persist_enroll_pending(
    engine: Engine, job: JobRow, assessment_id: str, rev: int, identity_result: dict[str, Any]
) -> bool:
    with fenced_business_tx(engine, job) as conn:
        res = conn.execute(
            _PERSIST_ENROLL_PENDING,
            {"id": assessment_id, "rev": rev, "identity_result": _json(identity_result)},
        )
        return res.rowcount > 0


def _mark_failed(
    engine: Engine, job: JobRow, assessment_id: str, rev: int, code: str, reason: str
) -> None:
    # failure_detail 仅内部诊断（裁定 3）：只留脱敏 reason，不承载协议字段
    detail = {"reason": str(reason)[:200]}
    with fenced_business_tx(engine, job) as conn:
        conn.execute(
            _MARK_FAILED,
            {"id": assessment_id, "rev": rev, "code": code, "detail": _json(detail)},
        )


def _find_member(engine: Engine, namespace: str, face_subject_ref: Optional[str]) -> Optional[str]:
    if not isinstance(face_subject_ref, str) or not face_subject_ref:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            _SELECT_MEMBER_BY_REF, {"ns": namespace, "ref": face_subject_ref}
        ).first()
    return str(row[0]) if row is not None else None


def _publish(
    conn: Connection,
    *,
    assessment_id: str,
    rev: int,
    member_id: str,
    report_id: str,
    report_summary: dict[str, Any],
    report_payload: dict[str, Any],
    identity_result: dict[str, Any],
    max_attempts: int,
) -> None:
    locked = conn.execute(
        _SELECT_ASSESSMENT_FOR_UPDATE, {"id": assessment_id}
    ).mappings().first()
    if locked is None:
        return
    if int(locked["processing_revision"]) != rev:
        return
    if locked["status"] == "report_ready":
        return
    res = conn.execute(
        _UPDATE_PUBLISH,
        {
            "id": assessment_id,
            "rev": rev,
            "member_id": member_id,
            "report_id": report_id,
            "report_summary": _json(report_summary),
            "report_payload": _json(report_payload),
            "report_photo_version": int(locked["current_photo_version"]),
            "identity_result": _json(identity_result),
        },
    )
    if res.rowcount == 0:
        return
    plan_id = str(uuid.uuid4())
    plan_summary = {
        "schema_version": 1,
        "source_report_id": report_id,
        "source_report_ready_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    inserted = conn.execute(
        _INSERT_PLAN,
        {
            "id": plan_id,
            "assessment_id": assessment_id,
            "member_id": member_id,
            "input_photo_version": int(locked["current_photo_version"]),
            "plan_summary": _json(plan_summary),
        },
    ).first()
    if inserted is None:
        existing = conn.execute(_SELECT_PLAN_ID, {"assessment_id": assessment_id}).first()
        if existing is None:
            return
        plan_id = str(existing[0])
    insert_job(
        conn,
        job_type="plan.generate",
        dedup_key=f"plan:{plan_id}:0",
        owner_type="plan",
        owner_id=plan_id,
        input_revision=0,
        payload={"schema_version": 1, "plan_id": plan_id, "generation_revision": "0"},
        max_attempts=max_attempts,
    )


handler = AssessmentAnalyzeHandler()

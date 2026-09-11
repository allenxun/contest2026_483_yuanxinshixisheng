"""``plan.generate`` handler 覆盖：defer 合法等待、能力匹配、冻结快照校验、K 保护、幂等。"""
from __future__ import annotations

import copy
import json
import logging
import uuid
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    count_jobs_by_dedup,
    fetch_plan,
    make_ctx,
    mark_report_ready,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_microcrystal,
    seed_plan,
)
from mvp_worker.handlers.dshared.dconfig import (
    DEFAULT_PLAN_CAPABILITY_BASELINE,
    DConfig,
)
from mvp_worker.handlers.dshared.providers import PlanDouble
from mvp_worker.handlers.plan_generate import _frozen_rules
from mvp_worker.handlers.plan_generate import handler as plan_handler
from mvp_worker.media.storage import FilesystemStorageDouble
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import StaleGeneration, complete_deferred


def _tiny_dcfg(*, wait: int) -> DConfig:
    return replace(DConfig.from_env(), plan_wait_check_seconds=wait)


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


def _seed_plan_case(
    engine: Engine,
    tmp_path: Any,
    *,
    plan_status: str = "waiting_inputs",
    input_pv: int = 1,
    gen_rev: int = 0,
    with_capability: bool = False,
    report_ready: bool = True,
    completed_count: int = 0,
    completed_at: bool = False,
    progress_revision: int = 0,
    input_snapshot: dict[str, Any] | None = None,
) -> tuple[Any, str, str, str, str | None]:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=1)
    member_id = seed_member(engine, ns=DEFAULT_NS, ref=str(uuid.uuid4()), assessment_id=aid)
    if report_ready:
        mark_report_ready(engine, aid, member_id=member_id, report_photo_version=input_pv)
    pid = seed_plan(
        engine,
        assessment_id=aid,
        member_id=member_id,
        generation_status=plan_status,
        input_photo_version=input_pv,
        generation_revision=gen_rev,
        completed_count=completed_count,
        completed_at=completed_at,
        progress_revision=progress_revision,
        input_snapshot=input_snapshot,
    )
    micro_id = seed_microcrystal(engine) if with_capability else None
    return storage, aid, member_id, pid, micro_id


def _enqueue_plan(
    engine: Engine,
    pid: str,
    rev: int,
    *,
    max_attempts: int = 5,
    dedup_key: str | None = None,
) -> str:
    jid, _ = enqueue(
        engine,
        job_type="plan.generate",
        dedup_key=dedup_key or f"plan:{pid}:{rev}",
        owner_type="plan",
        owner_id=pid,
        input_revision=rev,
        payload={"schema_version": 1, "plan_id": pid, "generation_revision": str(rev)},
        max_attempts=max_attempts,
    )
    return jid


def _frozen_snapshot() -> dict[str, Any]:
    """构造与默认批准基线一致的合法冻结 input_snapshot（含 ranges/regions/bounds）。"""
    base = DEFAULT_PLAN_CAPABILITY_BASELINE
    return {
        "schema_version": 1,
        "report": {
            "assessment_id": str(uuid.uuid4()),
            "report_id": str(uuid.uuid4()),
            "report_photo_version": 1,
        },
        "capability": {
            "microcrystal_id": str(uuid.uuid4()),
            "capability_id": base["capability_id"],
            "capability_revision": int(base["revision"]),
            "parameter_ranges": copy.deepcopy(base["parameter_ranges"]),
            "approved_regions": list(base["approved_regions"]),
            "n_bounds": dict(base["n_bounds"]),
        },
        "model": {
            "plan_provider": "double",
            "model_version": "double",
            "prompt_template_version": "1",
        },
    }


def test_plan_capability_missing_defer_burns_no_budget(
    engine: Engine, tmp_path: Any
) -> None:
    """能力缺失 → 每次 claim+defer 循环：attempt_count 回到基线、generation_revision 恒定。

    ≥3 个循环证明 defer 退还本次 claim 的 attempt（等待不烧预算），且无后继任务。
    """
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=5)
    dcfg = _tiny_dcfg(wait=0)
    extras = {"storage": storage, "plan_port": PlanDouble(), "dconfig": dcfg}
    baseline_attempts = int(fetch_job(engine, jid)["attempt_count"])
    assert baseline_attempts == 0

    for _ in range(3):
        status, exc, claim = run_claimed(engine, plan_handler, jid, extras=extras)
        assert status == "deferred" and exc is None
        assert claim.attempt_count == 1  # claim 本次 +1
        row = fetch_job(engine, jid)
        assert row["status"] == "queued"
        assert row["lease_owner"] is None
        assert row["lease_until"] is None
        assert int(row["attempt_count"]) == baseline_attempts  # 已退还
        assert int(row["lease_revision"]) == claim.lease_revision + 1  # 作废旧代次
        assert row["last_error"] is None  # 诊断字段不参与 defer

    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "waiting_inputs"
    assert plan["generation_revision"] == 0  # never advanced by worker
    assert plan["plan_payload"] is None
    assert count_jobs_by_dedup(engine, f"plan:{pid}:1") == 0  # NO successor job row


def test_plan_capability_appears_next_cycle_ready(engine: Engine, tmp_path: Any) -> None:
    """能力在下一 claim 周期出现 → 同一 job/同一 generation_revision 推进 ready。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=5)
    dcfg = _tiny_dcfg(wait=0)
    extras = {"storage": storage, "plan_port": PlanDouble(), "dconfig": dcfg}

    status, exc, _ = run_claimed(engine, plan_handler, jid, extras=extras)
    assert status == "deferred" and exc is None
    assert fetch_plan(engine, pid)["generation_status"] == "waiting_inputs"

    # 能力设备就绪（覆盖批准基线）→ 下一周期直接生成
    micro_id = seed_microcrystal(engine)
    status2, exc2, _ = run_claimed(engine, plan_handler, jid, extras=extras)
    assert status2 == "succeeded" and exc2 is None
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "ready"
    assert plan["generation_revision"] == 0  # unchanged across the wait
    assert plan["plan_payload"] is not None
    assert plan["target_count"] == 30
    assert plan["input_snapshot"]["capability"]["microcrystal_id"] == micro_id
    assert int(fetch_job(engine, jid)["attempt_count"]) == 1  # ready 那次消耗 1 次


def test_plan_capability_satisfied_ready(engine: Engine, tmp_path: Any) -> None:
    storage, _aid, _member, pid, micro_id = _seed_plan_case(
        engine, tmp_path, with_capability=True
    )
    jid = _enqueue_plan(engine, pid, 0)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "succeeded" and exc is None
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "ready"
    assert plan["target_count"] == 30
    assert plan["plan_payload"]["schema_version"] == 1
    assert len(plan["plan_payload"]["steps"]) >= 1
    for step in plan["plan_payload"]["steps"]:
        assert step["region"] in {"forehead", "left_cheek", "right_cheek", "nose"}
    assert plan["plan_summary"]["target_count"] == "30"
    assert plan["plan_summary"]["source_report_id"] is not None
    snap = plan["input_snapshot"]
    assert snap["schema_version"] == 1
    assert snap["capability"]["microcrystal_id"] == micro_id
    assert snap["capability"]["capability_id"] == "mvp-double-capability"
    assert snap["capability"]["capability_revision"] == 1
    # B1：批准区域与 N 边界随生成转换一次冻结
    assert snap["capability"]["approved_regions"] == [
        "forehead", "left_cheek", "right_cheek", "nose"
    ]
    assert snap["capability"]["n_bounds"] == {"min": 1, "max": 100}
    assert snap["capability"]["parameter_ranges"] == DEFAULT_PLAN_CAPABILITY_BASELINE[
        "parameter_ranges"
    ]
    assert snap["model"]["plan_provider"] == "double"
    # generation_revision 建行后永不变更（裁定 4）
    assert plan["generation_revision"] == 0
    # never touches K ledger
    assert plan["completed_count"] == 0
    assert plan["progress_revision"] == 0
    assert plan["completed_at"] is None


def test_plan_ready_publish_protects_k_ledger(engine: Engine, tmp_path: Any) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, with_capability=True, completed_count=5,
        completed_at=True, progress_revision=3,
    )
    before = fetch_plan(engine, pid)
    jid = _enqueue_plan(engine, pid, 0)
    status, _exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "succeeded"
    after = fetch_plan(engine, pid)
    assert after["generation_status"] == "ready"
    assert after["completed_count"] == 5
    assert after["progress_revision"] == 3
    assert after["completed_at"] is not None
    assert after["completed_at"] == before["completed_at"]


def test_plan_scan_ignores_malformed_revision_rows(engine: Engine, tmp_path: Any) -> None:
    """单行非数字 revision 不得毒化扫描：有效行仍被选中并发布 ready。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path, with_capability=True)
    # matching capability_id but non-numeric/structured revisions, fresh observation
    seed_microcrystal(engine, revision="abc")
    seed_microcrystal(engine, revision={"bad": 1})
    jid = _enqueue_plan(engine, pid, 0)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "succeeded" and exc is None
    assert fetch_plan(engine, pid)["generation_status"] == "ready"


def test_plan_scan_only_malformed_defers(engine: Engine, tmp_path: Any) -> None:
    """只有脏 revision 行时：不抛异常，返回 defer（无 wait-hop、无代次增长、不烧预算）。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path)
    seed_microcrystal(engine, revision="abc")
    seed_microcrystal(engine, revision={"bad": 1})
    jid = _enqueue_plan(engine, pid, 0)
    dcfg = _tiny_dcfg(wait=0)
    status, exc, claim = run_claimed(
        engine, plan_handler, jid,
        extras={"storage": storage, "plan_port": PlanDouble(), "dconfig": dcfg},
    )
    assert status == "deferred" and exc is None
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "waiting_inputs"
    assert plan["generation_revision"] == 0
    assert count_jobs_by_dedup(engine, f"plan:{pid}:1") == 0
    row = fetch_job(engine, jid)
    assert row["status"] == "queued"
    assert int(row["attempt_count"]) == 0  # refunded
    assert int(row["lease_revision"]) == claim.lease_revision + 1


def test_plan_scan_non_covering_device_keeps_deferring(
    engine: Engine, tmp_path: Any
) -> None:
    """B3：capability_id/revision 匹配但参数包络不覆盖基线 → 不构成有效确认，继续等待。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path)
    # 同名参数但设备包络更窄（min 更高 / max 更低）→ 不覆盖
    seed_microcrystal(
        engine,
        parameter_ranges={
            "intensity": {"unit": "percent", "min": 10.0, "max": 90.0},
            "duration": {"unit": "second", "min": 1.0, "max": 600.0},
            "pulse_count": {"unit": "count", "min": 1.0, "max": 1000.0},
        },
    )
    jid = _enqueue_plan(engine, pid, 0, max_attempts=5)
    dcfg = _tiny_dcfg(wait=0)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid,
        extras={"storage": storage, "plan_port": PlanDouble(), "dconfig": dcfg},
    )
    assert status == "deferred" and exc is None
    assert fetch_plan(engine, pid)["generation_status"] == "waiting_inputs"

    # 出现覆盖包络的设备 → 下一周期推进
    seed_microcrystal(engine)  # 默认覆盖批准基线
    status2, exc2, _ = run_claimed(
        engine, plan_handler, jid,
        extras={"storage": storage, "plan_port": PlanDouble(), "dconfig": dcfg},
    )
    assert status2 == "succeeded" and exc2 is None
    assert fetch_plan(engine, pid)["generation_status"] == "ready"


@pytest.mark.parametrize(
    "invalid",
    [
        "n_zero",
        "n_too_large",
        "unknown_region",
        "param_out_of_range",
        "extra_property",
        "n_string_garbage",
        "unknown_param",
        "bad_parameters_shape",
        "empty_steps",
    ],
)
def test_plan_invalid_never_ready(engine: Engine, tmp_path: Any, invalid: str) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path, with_capability=True)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=1)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid,
        extras={"storage": storage, "plan_port": PlanDouble(invalid=invalid)},
    )
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_VALIDATION_FAILED" and exc.retryable is False
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"
    assert plan["plan_payload"] is None
    assert plan["target_count"] is None
    detail = plan["failure_detail"]
    assert detail["code"] == "PLAN_VALIDATION_FAILED"
    assert detail["retryable"] is False
    assert isinstance(detail["violations"], list) and detail["violations"]
    # violations only carry json_paths (no leaked values)
    assert all(isinstance(v, str) and v.startswith("$") for v in detail["violations"])


def test_plan_invalid_retryable_before_last_attempt(engine: Engine, tmp_path: Any) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path, with_capability=True)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=3)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid,
        extras={"storage": storage, "plan_port": PlanDouble(invalid="n_zero")},
    )
    assert status == "failed" and exc is not None
    assert exc.retryable is True
    assert fetch_job(engine, jid)["status"] == "queued"
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "generating"  # retryable, not terminal
    assert plan["plan_payload"] is None


@pytest.mark.parametrize(
    "bad_steps",
    [
        [{"region": "forehead", "parameters": {"intensity": 40}}],  # missing step_id
        [{"step_id": "", "region": "forehead", "parameters": {"intensity": 40}}],
        [{"step_id": "x" * 65, "region": "forehead", "parameters": {"intensity": 40}}],
    ],
)
def test_plan_invalid_step_id_never_ready(
    engine: Engine, tmp_path: Any, bad_steps: list[dict[str, Any]]
) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path, with_capability=True)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=1)
    port = PlanDouble(steps=bad_steps)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": port}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_VALIDATION_FAILED" and exc.retryable is False
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"
    assert plan["plan_payload"] is None
    assert any("step_id" in v for v in plan["failure_detail"]["violations"])


def test_plan_generating_snapshot_missing_terminal(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """B2：generating 重试时快照缺失 → 终态 PLAN_SNAPSHOT_INVALID，绝不回落 live 配置。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, plan_status="generating", with_capability=True, input_snapshot={}
    )
    # 即使 live 配置完好，也不得据其继续
    jid = _enqueue_plan(engine, pid, 0, max_attempts=3)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_SNAPSHOT_INVALID" and exc.retryable is False
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"
    assert plan["failure_detail"]["code"] == "PLAN_SNAPSHOT_INVALID"
    assert plan["generation_revision"] == 0
    assert plan["plan_payload"] is None
    assert fetch_job(engine, jid)["status"] == "failed"


def test_plan_generating_snapshot_malformed_terminal(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """B2：快照缺 frozen approved_regions/n_bounds → 终态 PLAN_SNAPSHOT_INVALID + ERROR 日志。"""
    snap = _frozen_snapshot()
    del snap["capability"]["approved_regions"]
    del snap["capability"]["n_bounds"]
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, plan_status="generating", with_capability=True, input_snapshot=snap
    )
    jid = _enqueue_plan(engine, pid, 0, max_attempts=1)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_SNAPSHOT_INVALID" and exc.retryable is False
    assert fetch_plan(engine, pid)["generation_status"] == "failed"


def test_plan_validation_uses_frozen_snapshot_ignores_live_config(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """B2：generating 重试一律以冻结快照校验；live 配置变更后仍按冻结规则通过。"""
    snap = _frozen_snapshot()
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, plan_status="generating", with_capability=True, input_snapshot=snap
    )
    # live 基线改为仅 forehead / N<=1 / 参数极窄 —— 若误用 live，PlanDouble 必违规
    narrow = {
        "schema_version": 1,
        "capability_id": "mvp-double-capability",
        "revision": 1,
        "parameter_ranges": {"intensity": {"unit": "percent", "min": 0.0, "max": 1.0}},
        "approved_regions": ["forehead"],
        "n_bounds": {"min": 1, "max": 1},
    }
    monkeypatch.setenv("MVP_PLAN_CAPABILITY_BASELINE", json.dumps(narrow))
    jid = _enqueue_plan(engine, pid, 0)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "succeeded" and exc is None
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "ready"
    assert plan["target_count"] == 30  # 冻结 n_bounds 允许
    regions = {s["region"] for s in plan["plan_payload"]["steps"]}
    assert "left_cheek" in regions  # 冻结 approved_regions 允许（narrow live 仅有 forehead）


def test_plan_provider_failure_consumes_attempt(engine: Engine, tmp_path: Any) -> None:
    """真实 provider 失败走 complete_failure：可重试重排且 attempt_count 增长（不退还）。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path, with_capability=True)

    class _BoomPlan:
        provider_name = "double"
        model_version = "double"

        def generate(self, *_a: Any, **_k: Any) -> Any:
            raise RuntimeError("provider exploded")

    jid = _enqueue_plan(engine, pid, 0, max_attempts=5)
    status, exc, claim = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": _BoomPlan()}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "DEPENDENCY_UNAVAILABLE" and exc.retryable is True
    row = fetch_job(engine, jid)
    assert row["status"] == "queued"
    assert int(row["attempt_count"]) == claim.attempt_count == 1  # 真失败保留 +1
    assert fetch_plan(engine, pid)["generation_status"] == "generating"


def test_plan_defer_guard_rolls_back_on_concurrent_t06_change(
    engine: Engine, tmp_path: Any
) -> None:
    """claim 后 T06 被并发改动 → defer 守卫 StaleGeneration：整体回滚、不重排、不退款。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=5)
    dcfg = _tiny_dcfg(wait=0)

    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=50)
    claim = next(c for c in claims if c.id == jid)
    ctx = make_ctx(
        engine,
        claim,
        extras={"storage": storage, "plan_port": PlanDouble(), "dconfig": dcfg},
    )
    result = plan_handler.handle(ctx, claim)
    assert result is not None and result.defer_seconds is not None

    # claim 与 defer 之间并发翻转 T06 业务状态
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE care_plans SET generation_status = 'failed'"
                " WHERE id = CAST(:id AS uuid)"
            ),
            {"id": pid},
        )

    with pytest.raises(StaleGeneration):
        complete_deferred(
            engine,
            claim,
            defer_seconds=float(result.defer_seconds),
            business_tx=result.business_tx,
        )

    row = fetch_job(engine, jid)
    assert row["status"] == "running"  # 未重排
    assert int(row["attempt_count"]) == claim.attempt_count  # 未退款
    assert int(row["lease_revision"]) == claim.lease_revision  # 未提升代次
    assert fetch_plan(engine, pid)["generation_status"] == "failed"


def test_plan_ready_rerun_noop(engine: Engine, tmp_path: Any) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path, with_capability=True)
    jid = _enqueue_plan(engine, pid, 0)
    run_claimed(engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()})
    before = fetch_plan(engine, pid)
    assert before["generation_status"] == "ready"

    jid2 = _enqueue_plan(engine, pid, 0, dedup_key=f"plan:{pid}:0:rerun")
    status2, _exc2, _ = run_claimed(
        engine, plan_handler, jid2, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status2 == "succeeded"
    after = fetch_plan(engine, pid)
    assert after["generation_revision"] == before["generation_revision"]
    assert after["plan_payload"] == before["plan_payload"]
    assert after["target_count"] == before["target_count"]


def test_plan_stale_generation_noop(engine: Engine, tmp_path: Any) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, with_capability=True, gen_rev=1
    )
    jid = _enqueue_plan(engine, pid, 0)  # stale job revision
    status, _exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "succeeded"
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "waiting_inputs"
    assert plan["generation_revision"] == 1
    assert plan["plan_payload"] is None


def test_plan_report_input_invalid_terminal(engine: Engine, tmp_path: Any) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, with_capability=True, report_ready=False
    )
    jid = _enqueue_plan(engine, pid, 0)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "REPORT_INPUT_INVALID" and exc.retryable is False
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"
    assert plan["failure_detail"]["code"] == "REPORT_INPUT_INVALID"


def test_plan_missing_terminal(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    missing = str(uuid.uuid4())
    jid = _enqueue_plan(engine, missing, 0)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_NOT_FOUND" and exc.retryable is False


def test_plan_dedup_single_row(engine: Engine, tmp_path: Any) -> None:
    storage, _aid, _member, pid, _ = _seed_plan_case(engine, tmp_path)
    dedup = f"plan:{pid}:0"
    jid1, replayed1 = enqueue(
        engine, job_type="plan.generate", dedup_key=dedup, owner_type="plan",
        owner_id=pid, input_revision=0,
        payload={"schema_version": 1, "plan_id": pid, "generation_revision": "0"},
    )
    jid2, replayed2 = enqueue(
        engine, job_type="plan.generate", dedup_key=dedup, owner_type="plan",
        owner_id=pid, input_revision=0,
        payload={"schema_version": 1, "plan_id": pid, "generation_revision": "0"},
    )
    assert replayed1 is False and replayed2 is True
    assert jid1 == jid2
    assert count_jobs_by_dedup(engine, dedup) == 1


# ------------------------------------------------ R2 frozen snapshot contract


def _mut_missing_report(snap: dict[str, Any]) -> None:
    del snap["report"]


def _mut_missing_model(snap: dict[str, Any]) -> None:
    del snap["model"]


def _mut_missing_capability_id(snap: dict[str, Any]) -> None:
    del snap["capability"]["capability_id"]


def _mut_n_bounds_min_invalid(snap: dict[str, Any]) -> None:
    snap["capability"]["n_bounds"]["min"] = "invalid"


def _mut_ranges_entry_non_object(snap: dict[str, Any]) -> None:
    snap["capability"]["parameter_ranges"]["intensity"] = "not-an-object"


def _mut_empty_unit(snap: dict[str, Any]) -> None:
    snap["capability"]["parameter_ranges"]["intensity"]["unit"] = ""


def _mut_min_gt_max(snap: dict[str, Any]) -> None:
    snap["capability"]["parameter_ranges"]["intensity"]["min"] = 200.0


def _mut_n_bounds_max_lt_min(snap: dict[str, Any]) -> None:
    snap["capability"]["n_bounds"] = {"min": 5, "max": 1}


def _mut_regions_empty(snap: dict[str, Any]) -> None:
    snap["capability"]["approved_regions"] = []


@pytest.mark.parametrize(
    "mutator",
    [
        _mut_missing_report,
        _mut_missing_model,
        _mut_missing_capability_id,
        _mut_n_bounds_min_invalid,
        _mut_ranges_entry_non_object,
        _mut_empty_unit,
        _mut_min_gt_max,
        _mut_n_bounds_max_lt_min,
        _mut_regions_empty,
    ],
    ids=[
        "missing_report",
        "missing_model",
        "missing_capability_id",
        "n_bounds_min_invalid",
        "ranges_entry_non_object",
        "empty_unit",
        "min_gt_max",
        "n_bounds_max_lt_min",
        "regions_empty",
    ],
)
def test_plan_frozen_snapshot_contract_violation_terminal(
    engine: Engine, tmp_path: Any, caplog: Any, mutator: Any
) -> None:
    """R2：冻结快照任一契约字段缺失/畸形 → fenced PLAN_SNAPSHOT_INVALID 终态。

    断言 T12 failed、T06 failed（非 stranded ``generating``）、ERROR 日志、
    未 publish ready、且非 ``HANDLER_ERROR``（无未处理异常）。
    """
    snap = _frozen_snapshot()
    mutator(snap)
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, plan_status="generating", with_capability=True,
        input_snapshot=snap,
    )
    jid = _enqueue_plan(engine, pid, 0, max_attempts=1)
    caplog.set_level(logging.ERROR, logger="mvp_worker.handlers.plan_generate")
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_SNAPSHOT_INVALID" and exc.retryable is False
    assert exc.code != "HANDLER_ERROR"
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"  # 非 stranded 'generating'
    assert plan["plan_payload"] is None
    assert plan["failure_detail"]["code"] == "PLAN_SNAPSHOT_INVALID"
    assert fetch_job(engine, jid)["status"] == "failed"
    assert any("plan.snapshot_invalid" in r.message for r in caplog.records)


def test_frozen_rules_rejects_schema_version_wrong_type() -> None:
    """schema_version 非整数（"1"/bool）→ None。

    DB CHECK ``ck_plan_input_snapshot_schema`` 不允许持久化该畸形快照，无法走
    SQL seed 的 job 级路径，故在此直接验证 ``_frozen_rules`` 拒绝 + 合法基线条通过。
    """
    wrong_str = _frozen_snapshot()
    wrong_str["schema_version"] = "1"
    assert _frozen_rules(wrong_str) is None
    wrong_bool = _frozen_snapshot()
    wrong_bool["schema_version"] = True
    assert _frozen_rules(wrong_bool) is None
    assert _frozen_rules(_frozen_snapshot()) is not None


# ---------------------------------------------------------- N2 convergence


def test_plan_terminal_failed_same_rev_converges_t12(
    engine: Engine, tmp_path: Any
) -> None:
    """N2：T06 本代次已 failed 而 T12 停同代次 → 重放收敛 T12 failed（不再 no-op 成功）。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, plan_status="failed", gen_rev=0
    )
    jid = _enqueue_plan(engine, pid, 0, max_attempts=1)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "failed" and exc is not None
    assert exc.code == "PLAN_GENERATION_FAILED" and exc.retryable is False
    row = fetch_job(engine, jid)
    assert row["status"] == "failed"
    assert row["last_error"]["code"] == "PLAN_GENERATION_FAILED"
    assert fetch_plan(engine, pid)["generation_status"] == "failed"  # T06 不变


def test_plan_terminal_failed_different_rev_noop(
    engine: Engine, tmp_path: Any
) -> None:
    """不同代次终态：保持 stale no-op（T12 succeeded，T06 不变）。"""
    storage, _aid, _member, pid, _ = _seed_plan_case(
        engine, tmp_path, plan_status="failed", gen_rev=1
    )
    jid = _enqueue_plan(engine, pid, 0)
    status, exc, _ = run_claimed(
        engine, plan_handler, jid, extras={"storage": storage, "plan_port": PlanDouble()}
    )
    assert status == "succeeded" and exc is None
    assert fetch_job(engine, jid)["status"] == "succeeded"
    assert fetch_plan(engine, pid)["generation_status"] == "failed"

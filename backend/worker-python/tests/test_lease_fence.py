"""B1 租约围栏证据：standalone 业务写在租约失效（回收/代次提升）后不得提交。

oracle round-1 BLOCKER：旧 worker 租约过期被回收、新 owner 接管后，daemon 的
standalone 业务写（状态标记/阶段持久化/终态标记）只按 processing_revision/status
守卫，仍可能把 T05 写成 failed/needs_retake 等终态污染新 owner 的任务。本文件证明
``dshared.dfence.fenced_business_tx`` 会整体拒绝这些写，且新 owner 仍能正常完成。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue
from d_support import (
    clean_d_tables,
    fetch_assessment,
    fetch_plan,
    make_ctx,
    photo_versions_for,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_media,
    seed_plan,
    seed_source_media,
)
from mvp_worker.handlers import JobFailed
from mvp_worker.handlers.assessment_analyze import (
    _persist_enroll_pending,
    handler as analyze_handler,
)
from mvp_worker.handlers.dshared.dfence import fenced_business_tx
from mvp_worker.handlers.dshared.providers import FaceDouble, SkinDouble
from mvp_worker.handlers.identity_enroll import (
    _persist_started,
    handler as enroll_handler,
)
from mvp_worker.handlers.media_cleanup import handler as cleanup_handler
from mvp_worker.handlers.plan_generate import handler as plan_handler
from mvp_worker.media.storage import FilesystemStorageDouble
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import (
    StaleGeneration,
    complete_failure,
    complete_success,
)
from mvp_worker.runtime.expire import recover_expired, release_claim


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


def _claim(engine: Engine, jid: str, *, worker: str = "w-stale") -> Any:
    claims = claim_batch(engine, worker_id=worker, lease_seconds=60, batch_size=50)
    claim = next((c for c in claims if c.id == jid), None)
    assert claim is not None, f"job {jid} not claimable"
    for other in claims:
        if other.id != jid:
            release_claim(engine, other, worker_id=worker)
    return claim


def _bump_revision(engine: Engine, jid: str) -> None:
    """模拟 reclaim：lease_revision+1 使旧 claim 代次失效（status 仍 running）。"""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET lease_revision = lease_revision + 1 WHERE id = :id"),
            {"id": jid},
        )


def _enqueue(engine: Engine, **kw: Any) -> str:
    jid, _ = enqueue(engine, **kw)
    return jid


def _extras(storage: Any, face: Any, skin: Any = None) -> dict[str, Any]:
    return {"storage": storage, "face_port": face, "skin_port": skin or SkinDouble()}


def _attach_photo_versions(
    engine: Engine, assessment_id: str, version: int, images: dict[str, str]
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET photo_versions = CAST(:pv AS jsonb)"
                " WHERE id = CAST(:id AS uuid)"
            ),
            {"pv": json.dumps(photo_versions_for(version, images)), "id": assessment_id},
        )


# ------------------------------------------------------------------ fence unit


def test_fenced_business_tx_allows_live_and_blocks_stale_lease(
    engine: Engine, tmp_path: Any
) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, _key = seed_media(engine, storage, state="available")
    jid = _enqueue(engine, job_type="system.echo")
    claim = _claim(engine, jid)

    # 活跃租约：围栏内业务写提交
    with fenced_business_tx(engine, claim) as conn:
        conn.execute(
            text("UPDATE media_objects SET state = 'pending' WHERE id = CAST(:id AS uuid)"),
            {"id": mid},
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT state FROM media_objects WHERE id = CAST(:id AS uuid)"), {"id": mid}
        ).scalar_one() == "pending"

    # 代次失效：围栏拒绝，业务写不得提交
    _bump_revision(engine, jid)
    with pytest.raises(StaleGeneration):
        with fenced_business_tx(engine, claim) as conn:
            conn.execute(
                text("UPDATE media_objects SET state = 'failed' WHERE id = CAST(:id AS uuid)"),
                {"id": mid},
            )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT state FROM media_objects WHERE id = CAST(:id AS uuid)"), {"id": mid}
        ).scalar_one() == "pending"


# ------------------------------------------------------------------ analyze B1


def test_analyze_stale_claim_terminal_failed_mark_rejected(engine: Engine) -> None:
    aid = seed_assessment(engine, status="analyzing", current_photo_version=1, processing_revision=2)
    jid = _enqueue(
        engine,
        job_type="assessment.analyze",
        owner_type="assessment",
        owner_id=aid,
        input_revision=2,
        payload={"schema_version": 1, "assessment_id": aid, "processing_revision": "2"},
    )
    claim = _claim(engine, jid)
    ctx = make_ctx(engine, claim)
    _bump_revision(engine, jid)

    # 终态业务写 = JobFailed.business_tx（不再独立预提交）；随 complete_failure 原子围栏
    with pytest.raises(JobFailed) as ei:
        analyze_handler._terminal(
            ctx, claim, aid, 2,
            code="DEPENDENCY_UNAVAILABLE", message="boom", reason="boom",
        )
    with pytest.raises(StaleGeneration):
        complete_failure(
            engine, claim, code=ei.value.code, message=ei.value.message,
            retryable=ei.value.retryable, business_tx=ei.value.business_tx,
        )

    a = fetch_assessment(engine, aid)
    assert a["status"] == "analyzing"  # 业务终态未提交
    assert a["failure_code"] is None


def test_analyze_stale_claim_needs_retake_mark_rolls_back(engine: Engine) -> None:
    aid = seed_assessment(engine, status="analyzing", current_photo_version=1, processing_revision=2)
    jid = _enqueue(
        engine,
        job_type="assessment.analyze",
        owner_type="assessment",
        owner_id=aid,
        input_revision=2,
        payload={"schema_version": 1, "assessment_id": aid, "processing_revision": "2"},
    )
    claim = _claim(engine, jid)
    ctx = make_ctx(engine, claim)
    result = analyze_handler._retake_result(
        ctx, claim, aid, 2,
        classification="uncertain", code="IDENTITY_UNCERTAIN",
        required_views=["front"], detail="uncertain",
    )
    _bump_revision(engine, jid)

    with pytest.raises(StaleGeneration):
        complete_success(engine, claim, handler_result_tx=result.business_tx)

    a = fetch_assessment(engine, aid)
    assert a["status"] == "analyzing"  # needs_retake 未落库
    assert a["failure_code"] is None
    assert a["identity_result"] == {}  # 未写入 quality/classification


def test_analyze_stale_claim_phase_persist_rejected(engine: Engine) -> None:
    aid = seed_assessment(engine, status="analyzing", current_photo_version=1, processing_revision=2)
    jid = _enqueue(
        engine,
        job_type="assessment.analyze",
        owner_type="assessment",
        owner_id=aid,
        input_revision=2,
        payload={"schema_version": 1, "assessment_id": aid, "processing_revision": "2"},
    )
    claim = _claim(engine, jid)
    _bump_revision(engine, jid)

    with pytest.raises(StaleGeneration):
        _persist_enroll_pending(
            engine, claim, aid, 2, {"schema_version": 1, "phase": "enroll_pending"}
        )

    assert fetch_assessment(engine, aid)["identity_result"] == {}


# ------------------------------------------------------------------ enroll B1


def test_enroll_stale_claim_phase_persist_rejected(engine: Engine) -> None:
    aid = seed_assessment(engine, status="analyzing", current_photo_version=1, processing_revision=2)
    jid = _enqueue(
        engine,
        job_type="identity.enroll",
        owner_type="identity_namespace",
        owner_id=str(uuid.uuid4()),
        input_revision=2,
        payload={"schema_version": 1, "assessment_id": aid},
    )
    claim = _claim(engine, jid)
    _bump_revision(engine, jid)

    with pytest.raises(StaleGeneration):
        _persist_started(
            engine, claim, aid, 2, {"schema_version": 1, "phase": "enroll_started"}
        )

    assert fetch_assessment(engine, aid)["identity_result"] == {}


# ------------------------------------------------------------------ plan B1


def test_plan_stale_claim_terminal_mark_rejected(engine: Engine) -> None:
    aid = seed_assessment(engine)
    member_id = seed_member(engine, assessment_id=aid)
    pid = seed_plan(
        engine, assessment_id=aid, member_id=member_id,
        generation_status="waiting_inputs", generation_revision=0, input_photo_version=1,
    )
    jid = _enqueue(
        engine,
        job_type="plan.generate",
        owner_type="plan",
        owner_id=pid,
        input_revision=0,
        payload={"schema_version": 1, "plan_id": pid, "generation_revision": "0"},
    )
    claim = _claim(engine, jid)
    ctx = make_ctx(engine, claim)
    _bump_revision(engine, jid)

    with pytest.raises(JobFailed) as ei:
        plan_handler._terminal(
            ctx, claim, pid, 0,
            code="PLAN_VALIDATION_FAILED", message="boom", detail={"reason": "boom"},
        )
    with pytest.raises(StaleGeneration):
        complete_failure(
            engine, claim, code=ei.value.code, message=ei.value.message,
            retryable=ei.value.retryable, business_tx=ei.value.business_tx,
        )

    assert fetch_plan(engine, pid)["generation_status"] == "waiting_inputs"


# ------------------------------------------------------------------ cleanup B1


def test_cleanup_stale_claim_transition_rejected(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    jid = _enqueue(
        engine,
        job_type="media.cleanup",
        dedup_key=f"media:{mid}:cleanup:1",
        owner_type="media",
        owner_id=mid,
        input_revision=1,
        payload={"schema_version": 1, "media_object_id": mid, "cleanup_revision": "1"},
    )
    claim = _claim(engine, jid)
    _bump_revision(engine, jid)

    ctx = make_ctx(engine, claim, extras={"storage": storage})
    assert cleanup_handler.handle(ctx, claim) is None  # 围栏拒绝 → 干净返回

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT state FROM media_objects WHERE id = CAST(:id AS uuid)"), {"id": mid}
        ).scalar_one() == "available"
    assert storage.exists(key)


# ------------------------------------------------------------------ new owner


def test_stale_analyze_rejected_then_new_owner_completes(engine: Engine, tmp_path: Any) -> None:
    ref = str(uuid.uuid4())
    storage = FilesystemStorageDouble(tmp_path / "s")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=2)
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    seed_member(engine, ref=ref, assessment_id=aid)
    jid = _enqueue(
        engine,
        job_type="assessment.analyze",
        owner_type="assessment",
        owner_id=aid,
        input_revision=2,
        payload={"schema_version": 1, "assessment_id": aid, "processing_revision": "2"},
    )
    stale = _claim(engine, jid)

    # 租约过期 → 回收器重排（代次+1，status queued）
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP - make_interval(secs => 5)"
                " WHERE id = :id"
            ),
            {"id": jid},
        )
    assert recover_expired(engine) == 1
    ctx = make_ctx(
        engine, stale, extras=_extras(storage, FaceDouble(search="matched", face_subject_ref=ref))
    )
    assert analyze_handler.handle(ctx, stale) is None  # 旧代次：无业务写
    assert fetch_assessment(engine, aid)["status"] == "queued"

    status, exc, _ = run_claimed(
        engine, analyze_handler, jid,
        extras=_extras(storage, FaceDouble(search="matched", face_subject_ref=ref)),
    )
    assert status == "succeeded" and exc is None
    assert fetch_assessment(engine, aid)["status"] == "report_ready"

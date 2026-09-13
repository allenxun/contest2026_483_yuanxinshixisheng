"""``assessment.analyze`` handler 覆盖：发布、身份归档、补拍、失败/终止、幂等。"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    count_members,
    fetch_assessment,
    fetch_job_full_by_dedup,
    fetch_plan,
    fetch_result_media,
    photo_versions_for,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_source_media,
)
from mvp_worker.handlers import JobFailed, HandlerResult
from mvp_worker.handlers.assessment_analyze import handler as analyze_handler
from mvp_worker.handlers.dshared.constants import candidate_entity_id, namespace_owner_id
from mvp_worker.handlers.dshared.jsonschema_support import (
    load_payload_validator,
    validate_payload,
)
from mvp_worker.handlers.dshared.providers import (
    FaceDouble,
    ProviderUnavailable,
    SkinDouble,
)
from mvp_worker.handlers.identity_enroll import handler as enroll_handler
from mvp_worker.media.storage import (
    FilesystemStorageDouble,
    StorageConfigError,
    StorageError,
    StorageTransientError,
)
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import complete_success


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


def _extras(storage: Any, face: Any, skin: Any = None) -> dict[str, Any]:
    return {"storage": storage, "face_port": face, "skin_port": skin or SkinDouble()}


def _attach_photo_versions(
    engine: Engine, assessment_id: str, version: int, images: dict[str, str]
) -> None:
    payload = photo_versions_for(version, images)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET photo_versions = CAST(:pv AS jsonb)"
                " WHERE id = CAST(:id AS uuid)"
            ),
            {"pv": json.dumps(payload), "id": assessment_id},
        )


def _seed_analysis_case(
    engine: Engine,
    tmp_path: Any,
    *,
    ref: str | None = None,
    status: str = "queued",
    rev: int = 2,
) -> tuple[Any, str, dict[str, str], str | None]:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(
        engine, status=status, current_photo_version=1, processing_revision=rev
    )
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    member_id = None
    if ref is not None:
        member_id = seed_member(engine, ns=DEFAULT_NS, ref=ref, assessment_id=aid)
    return storage, aid, images, member_id


def _enqueue_analyze(
    engine: Engine, aid: str, rev: int, *, max_attempts: int = 5
) -> str:
    jid, _ = enqueue(
        engine,
        job_type="assessment.analyze",
        dedup_key=f"assessment:{aid}:{rev}",
        owner_type="assessment",
        owner_id=aid,
        input_revision=rev,
        payload={
            "schema_version": 1,
            "assessment_id": aid,
            "processing_revision": str(rev),
        },
        max_attempts=max_attempts,
    )
    return jid


def test_analyze_matched_publishes_report_and_hands_off_plan(
    engine: Engine, tmp_path: Any
) -> None:
    ref = str(uuid.uuid4())
    storage, aid, images, member_id = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "succeeded" and exc is None

    a = fetch_assessment(engine, aid)
    assert a["status"] == "report_ready"
    assert str(a["member_id"]) == member_id
    assert a["report_id"] is not None
    assert a["report_photo_version"] == 1
    assert a["report_ready_at"] is not None
    assert a["report_summary"]["schema_version"] == 1
    assert a["report_summary"]["conclusion"] == "balanced"
    assert isinstance(a["report_summary"]["headline_metrics"], list)
    assert a["report_payload"]["schema_version"] == 1
    assert {m["name"] for m in a["report_payload"]["metrics"]} <= {
        "moisture", "oiliness", "smoothness", "redness",
    }
    assert a["report_payload"]["model_info"]["skin_provider"] == "double"
    assert a["identity_result"]["classification"] == "matched"
    # 裁定 3：发布态 identity_result 也携带 quality（accepted/空 required_views）
    assert a["identity_result"]["quality"] == {"status": "accepted", "required_views": []}
    assert a["failure_detail"] is None
    assert len(a["report_payload"]["images"]) == 2

    # T06 waiting_inputs + plan job
    with engine.connect() as conn:
        prow = conn.execute(
            text("SELECT id FROM care_plans WHERE assessment_id = CAST(:a AS uuid)"),
            {"a": aid},
        ).first()
    assert prow is not None
    plan_id = str(prow[0])
    plan = fetch_plan(engine, plan_id)
    assert plan["generation_status"] == "waiting_inputs"
    assert plan["generation_revision"] == 0
    assert plan["input_photo_version"] == 1
    assert str(plan["member_id"]) == member_id

    pjob = fetch_job_full_by_dedup(engine, f"plan:{plan_id}:0")
    assert pjob["status"] == "queued"
    assert pjob["job_type"] == "plan.generate"
    assert pjob["owner_type"] == "plan"
    assert str(pjob["owner_id"]) == plan_id
    assert int(pjob["input_revision"]) == 0
    assert pjob["payload"]["generation_revision"] == "0"
    # 撤销过渡等待预算：plan 任务 max_attempts 回退 A 运行时默认
    from mvp_worker.config import WorkerConfig

    assert int(pjob["max_attempts"]) == WorkerConfig().retry_max_attempts

    analyze_job = fetch_job(engine, jid)
    assert analyze_job["status"] == "succeeded"
    assert int(analyze_job["attempt_count"]) == 1


def test_analyze_reliable_new_enroll_then_rerun_publishes(
    engine: Engine, tmp_path: Any
) -> None:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=2)
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="reliable_new")

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "failed" and exc is not None
    assert exc.code == "IDENTITY_ENROLLMENT_PENDING"
    assert exc.retryable is True
    # analyze requeued retryable
    assert fetch_job(engine, jid)["status"] == "queued"

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT id, job_type, owner_type, owner_id, input_revision, payload"
                " FROM async_jobs WHERE job_type = 'identity.enroll'"
            )
        ).mappings().first()
    assert row is not None
    assert row["owner_type"] == "identity_namespace"
    assert str(row["owner_id"]) == namespace_owner_id(DEFAULT_NS)
    assert int(row["input_revision"]) == 2
    validate_payload(
        load_payload_validator("payload-identity-enroll.json"),
        dict(row["payload"]),
        "payload-identity-enroll.json",
    )
    enroll_jid = str(row["id"])

    # run enroll
    status2, exc2, _ = run_claimed(
        engine, enroll_handler, enroll_jid, extras={"storage": storage, "face_port": face}
    )
    assert status2 == "succeeded" and exc2 is None
    assert count_members(engine, ns=DEFAULT_NS) == 1
    a = fetch_assessment(engine, aid)
    assert a["member_id"] is not None
    assert a["identity_result"]["phase"] == "enrolled"

    # re-run analyze (reclaimed, retryable attempt) → now search matches → publish
    status3, exc3, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status3 == "succeeded" and exc3 is None
    a = fetch_assessment(engine, aid)
    assert a["status"] == "report_ready"
    assert a["report_id"] is not None
    assert count_members(engine, ns=DEFAULT_NS) == 1  # enroll reused, no duplicate member


def test_analyze_reliable_new_slot_occupied_no_second_enroll(
    engine: Engine, tmp_path: Any
) -> None:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=2)
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    # pre-seed an unrelated pending enroll occupying the namespace slot
    enqueue(
        engine,
        job_type="identity.enroll",
        dedup_key=f"identity:{DEFAULT_NS}:other-candidate",
        owner_type="identity_namespace",
        owner_id=namespace_owner_id(DEFAULT_NS),
        input_revision=2,
        payload={"schema_version": 1},
    )
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="reliable_new")

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "failed" and exc is not None
    assert exc.code == "IDENTITY_ENROLLMENT_PENDING" and exc.retryable is True
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM async_jobs WHERE job_type = 'identity.enroll'")
        ).scalar_one()
    assert int(n) == 1  # no second enroll row
    a = fetch_assessment(engine, aid)
    assert a["identity_result"]["phase"] == "enroll_pending"


def test_analyze_reliable_new_last_attempt_terminal_timeout(
    engine: Engine, tmp_path: Any
) -> None:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=2)
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    jid = _enqueue_analyze(engine, aid, 2, max_attempts=1)
    face = FaceDouble(search="reliable_new")
    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "failed" and exc is not None
    assert exc.code == "IDENTITY_ENROLLMENT_TIMEOUT" and exc.retryable is False
    a = fetch_assessment(engine, aid)
    assert a["status"] == "failed"
    assert a["failure_code"] == "IDENTITY_ENROLLMENT_TIMEOUT"
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM async_jobs WHERE job_type = 'identity.enroll'")
        ).scalar_one()
    assert int(n) == 1  # enrollment coordination item remains (slot occupied)


def test_analyze_cross_cycle_reconciles_enrolled_member_with_fresh_face(
    engine: Engine, tmp_path: Any
) -> None:
    """真实循环链：analyze#1 → enroll → analyze#2（全新 face 实例、search 仍
    reliable_new）→ 依据 PG 成员行对账发布，不重复登记、不死循环。"""
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=2)
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    jid = _enqueue_analyze(engine, aid, 2)
    candidate_id = candidate_entity_id(DEFAULT_NS, aid)

    # cycle1：全新 FaceDouble#1（默认 reliable_new）→ 入队 enroll + analyze PENDING
    face1 = FaceDouble(search="reliable_new")
    status1, exc1, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face1))
    assert status1 == "failed" and exc1 is not None
    assert exc1.code == "IDENTITY_ENROLLMENT_PENDING" and exc1.retryable is True
    assert fetch_job(engine, jid)["status"] == "queued"
    enroll_jid = str(
        fetch_job_full_by_dedup(engine, f"identity:{DEFAULT_NS}:{candidate_id}")["id"]
    )

    # 运行 enroll（另一个全新 double，登记成功）→ 成员建立
    face_enroll = FaceDouble(search="reliable_new")
    status_e, exc_e, _ = run_claimed(
        engine, enroll_handler, enroll_jid,
        extras={"storage": storage, "face_port": face_enroll},
    )
    assert status_e == "succeeded" and exc_e is None
    assert count_members(engine, ns=DEFAULT_NS) == 1
    enrolled_member = str(fetch_assessment(engine, aid)["member_id"])
    assert enrolled_member not in ("", "None")

    # cycle2：全新 FaceDouble#2（同样 amnesia：search 仍 reliable_new）→ 对账发布
    face2 = FaceDouble(search="reliable_new")
    status2, exc2, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face2))
    assert status2 == "succeeded" and exc2 is None

    a = fetch_assessment(engine, aid)
    assert a["status"] == "report_ready"
    assert str(a["member_id"]) == enrolled_member
    assert a["identity_result"]["classification"] == "reliable_new"
    assert a["identity_result"]["phase"] == "enrolled_reconciled"
    assert a["identity_result"]["candidate_entity_id"] == candidate_id
    assert a["report_id"] is not None
    assert count_members(engine, ns=DEFAULT_NS) == 1  # 不重复建正式成员
    assert fetch_job(engine, jid)["status"] == "succeeded"

    # T06 waiting_inputs + plan:{id}:0 job
    with engine.connect() as conn:
        prow = conn.execute(
            text("SELECT id FROM care_plans WHERE assessment_id = CAST(:a AS uuid)"),
            {"a": aid},
        ).first()
    assert prow is not None
    plan_id = str(prow[0])
    assert fetch_plan(engine, plan_id)["generation_status"] == "waiting_inputs"
    assert fetch_job_full_by_dedup(engine, f"plan:{plan_id}:0")["status"] == "queued"


def test_analyze_reliable_new_reconcile_absent_with_slot_occupied_stays_pending(
    engine: Engine, tmp_path: Any
) -> None:
    """成员不存在 + namespace 未决登记槽被占 → 仍 PENDING retryable（行为不变）。"""
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=2)
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    # 预置一个无关候选占用 namespace 未决槽
    enqueue(
        engine,
        job_type="identity.enroll",
        dedup_key=f"identity:{DEFAULT_NS}:other-candidate",
        owner_type="identity_namespace",
        owner_id=namespace_owner_id(DEFAULT_NS),
        input_revision=2,
        payload={"schema_version": 1},
    )
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="reliable_new")

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "failed" and exc is not None
    assert exc.code == "IDENTITY_ENROLLMENT_PENDING" and exc.retryable is True
    # 候选成员本就不存在（对账不应短路），且不新增第二份登记
    assert count_members(engine, ns=DEFAULT_NS) == 0
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM async_jobs WHERE job_type = 'identity.enroll'")
        ).scalar_one()
    assert int(n) == 1
    a = fetch_assessment(engine, aid)
    assert a["identity_result"]["phase"] == "enroll_pending"


def test_analyze_uncertain_no_member(engine: Engine, tmp_path: Any) -> None:
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="uncertain")

    status, _exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "succeeded"
    a = fetch_assessment(engine, aid)
    assert a["status"] == "needs_retake"
    assert a["failure_code"] == "IDENTITY_UNCERTAIN"
    # 裁定 3：requiredViews 唯一权威通道 = identity_result.quality
    assert a["identity_result"]["quality"]["status"] == "needs_retake"
    assert a["identity_result"]["quality"]["required_views"] == ["front", "left", "right"]
    assert a["identity_result"]["classification"] == "uncertain"
    assert "required_views" not in a["failure_detail"]
    assert "retryable" not in a["failure_detail"]
    assert count_members(engine, ns=DEFAULT_NS) == 0


def test_analyze_quality_rejected_subset(engine: Engine, tmp_path: Any) -> None:
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(quality="needs_retake", required_views=("left",))

    status, _exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "succeeded"
    a = fetch_assessment(engine, aid)
    assert a["status"] == "needs_retake"
    assert a["failure_code"] == "QUALITY_REJECTED"
    assert a["identity_result"]["quality"]["status"] == "needs_retake"
    assert a["identity_result"]["quality"]["required_views"] == ["left"]
    assert set(a["identity_result"]["quality"]["required_views"]) <= {"front", "left", "right"}
    assert "required_views" not in a["failure_detail"]


def test_analyze_not_same_person_all_views(engine: Engine, tmp_path: Any) -> None:
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(same_person=False)

    status, _exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "succeeded"
    a = fetch_assessment(engine, aid)
    assert a["status"] == "needs_retake"
    assert a["failure_code"] == "NOT_SAME_PERSON"
    assert a["identity_result"]["quality"]["required_views"] == ["front", "left", "right"]
    assert "required_views" not in a["failure_detail"]


def test_analyze_stale_processing_revision_no_touch(engine: Engine, tmp_path: Any) -> None:
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path)
    jid = _enqueue_analyze(engine, aid, 2)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET processing_revision = 3"
                " WHERE id = CAST(:id AS uuid)"
            ),
            {"id": aid},
        )
    face = FaceDouble(search="matched", face_subject_ref=str(uuid.uuid4()))
    status, _exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "succeeded"
    assert fetch_job(engine, jid)["status"] == "succeeded"
    a = fetch_assessment(engine, aid)
    assert a["status"] == "queued"
    assert a["report_id"] is None
    assert face.calls.get("quality", 0) == 0  # no external call on stale input


def test_analyze_publish_guard_flip_between_handle_and_tx(
    engine: Engine, tmp_path: Any
) -> None:
    ref = str(uuid.uuid4())
    storage, aid, _images, member_id = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=20)
    claim = next(c for c in claims if c.id == jid)
    analyze_handler.validate(claim.payload)
    from d_support import make_ctx

    ctx = make_ctx(engine, claim, extras=_extras(storage, face))
    result = analyze_handler.handle(ctx, claim)
    assert isinstance(result, HandlerResult)
    # flip to needs_retake with same revision before business_tx
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET status='needs_retake'"
                " WHERE id = CAST(:id AS uuid)"
            ),
            {"id": aid},
        )
    complete_success(engine, claim, handler_result_tx=result.business_tx)
    a = fetch_assessment(engine, aid)
    assert a["status"] == "needs_retake"
    assert a["report_id"] is None
    assert a["report_payload"] is None
    assert fetch_job(engine, jid)["status"] == "succeeded"


def test_analyze_result_image_idempotent_on_retry(engine: Engine, tmp_path: Any) -> None:
    ref = str(uuid.uuid4())
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path, ref=ref)
    inner = FilesystemStorageDouble(tmp_path / "storage")
    faulty = _FailFirstStorage(inner, failures=1)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(faulty, face))
    assert status == "failed" and exc is not None
    assert exc.code == "RESULT_ARCHIVE_FAILED" and exc.retryable is True
    # N1 两阶段：put 在 PG 事务外；put 失败保留 pending 行（意图已持久化），重试
    # 复用同一行/key 续跑，成功仍恰一行/ref（advisory lock 串行 + 行复用）。
    pending = fetch_result_media(engine, aid, 1)
    assert len(pending) == 1 and pending[0]["state"] == "pending"

    status2, _exc2, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(inner, face))
    assert status2 == "succeeded"
    rows = fetch_result_media(engine, aid, 1)
    refs = [r["storage_metadata"].get("provider_ref") for r in rows]
    assert len(refs) == len(set(refs)) == 2
    assert set(refs) == {"skin-result-1", "skin-result-2"}
    assert all(r["state"] == "available" for r in rows)


def test_analyze_dependency_failure_retryable_stays_analyzing(
    engine: Engine, tmp_path: Any
) -> None:
    ref = str(uuid.uuid4())
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(
        search="matched",
        face_subject_ref=ref,
        faults={"search_1n": [ProviderUnavailable("down")]},
    )
    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "failed" and exc is not None
    assert exc.retryable is True
    assert fetch_job(engine, jid)["status"] == "queued"
    assert fetch_assessment(engine, aid)["status"] == "analyzing"


def test_analyze_last_attempt_terminal_marks_failed(engine: Engine, tmp_path: Any) -> None:
    ref = str(uuid.uuid4())
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2, max_attempts=1)
    skin = SkinDouble(faults={"analyze": [ProviderUnavailable("down")]})
    face = FaceDouble(search="matched", face_subject_ref=ref)
    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face, skin))
    assert status == "failed" and exc is not None
    assert exc.retryable is False
    a = fetch_assessment(engine, aid)
    assert a["status"] == "failed"
    assert a["failure_code"] == "DEPENDENCY_UNAVAILABLE"
    # 裁定 3：failure_detail 仅内部诊断（reason），不再承载 retryable/required_views
    assert isinstance(a["failure_detail"]["reason"], str)
    assert "retryable" not in a["failure_detail"]
    assert "required_views" not in a["failure_detail"]


def test_analyze_contract_violation_terminal(engine: Engine, tmp_path: Any) -> None:
    ref = str(uuid.uuid4())
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    skin = SkinDouble(invalid="unknown_metric")
    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face, skin))
    assert status == "failed" and exc is not None
    assert exc.code == "PROVIDER_CONTRACT_VIOLATION" and exc.retryable is False
    a = fetch_assessment(engine, aid)
    assert a["status"] == "failed"
    assert a["failure_code"] == "PROVIDER_CONTRACT_VIOLATION"
    assert a["report_id"] is None
    assert a["report_payload"] is None


def test_analyze_report_ready_rerun_noop(engine: Engine, tmp_path: Any) -> None:
    ref = str(uuid.uuid4())
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    status, _exc, _ = run_claimed(engine, analyze_handler, jid, extras=_extras(storage, face))
    assert status == "succeeded"
    before = fetch_assessment(engine, aid)
    before_json = json.dumps(
        {k: str(before[k]) for k in ("report_id", "report_payload", "report_summary",
                                     "report_photo_version", "report_ready_at")},
        sort_keys=True,
    )
    # re-run with a fresh dedup (same payload) → status already report_ready → no-op
    jid2, _ = enqueue(
        engine,
        job_type="assessment.analyze",
        dedup_key=f"assessment:{aid}:2:rerun",
        owner_type="assessment",
        owner_id=aid,
        input_revision=2,
        payload={"schema_version": 1, "assessment_id": aid, "processing_revision": "2"},
    )
    status2, _exc2, _ = run_claimed(engine, analyze_handler, jid2, extras=_extras(storage, face))
    assert status2 == "succeeded"
    after = fetch_assessment(engine, aid)
    after_json = json.dumps(
        {k: str(after[k]) for k in ("report_id", "report_payload", "report_summary",
                                    "report_photo_version", "report_ready_at")},
        sort_keys=True,
    )
    assert before_json == after_json


def test_face_double_forbidden_in_production(monkeypatch: Any) -> None:
    from mvp_worker.handlers.dshared.dconfig import DConfig
    from mvp_worker.handlers.dshared.providers import build_face_port, ProviderConfigError

    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "double")
    cfg = DConfig.from_env()
    with pytest.raises(ProviderConfigError):
        build_face_port(cfg, environment="production")


def test_aliyun_adapter_not_activated(monkeypatch: Any) -> None:
    from mvp_worker.handlers.dshared.dconfig import DConfig
    from mvp_worker.handlers.dshared.providers import (
        build_face_port,
        ProviderNotActivated,
    )

    monkeypatch.setenv("MVP_D_FACE_PROVIDER", "aliyun_face")
    monkeypatch.delenv("MVP_D_ALIYUN_ACTIVATED", raising=False)
    cfg = DConfig.from_env()
    port = build_face_port(cfg, environment="production")
    with pytest.raises(ProviderNotActivated):
        port.quality({"front": b"x"})


class _FailFirstStorage:
    def __init__(self, inner: FilesystemStorageDouble, failures: int = 1) -> None:
        self._inner = inner
        self._remaining = failures

    def put(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        if self._remaining > 0:
            self._remaining -= 1
            raise StorageError("injected put failure")
        self._inner.put(object_key, data, content_type=content_type)

    def get(self, object_key: str) -> bytes:
        return self._inner.get(object_key)


# ---------------------------------------------------------- N2 convergence


def test_analyze_terminal_failed_same_rev_converges_t12(
    engine: Engine, tmp_path: Any
) -> None:
    """N2：T05 本输入代次已 failed 而 T12 停同代次 → 重放收敛 T12 failed。"""
    aid = seed_assessment(
        engine, status="failed", current_photo_version=1, processing_revision=2
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET failure_code='DEPENDENCY_UNAVAILABLE'"
                " WHERE id=CAST(:id AS uuid)"
            ),
            {"id": aid},
        )
    jid = _enqueue_analyze(engine, aid, 2)
    status, exc, _ = run_claimed(
        engine, analyze_handler, jid,
        extras=_extras(FilesystemStorageDouble(tmp_path / "s"), FaceDouble()),
    )
    assert status == "failed" and exc is not None
    assert exc.code == "DEPENDENCY_UNAVAILABLE" and exc.retryable is False
    row = fetch_job(engine, jid)
    assert row["status"] == "failed"
    assert row["last_error"]["code"] == "DEPENDENCY_UNAVAILABLE"  # == 持久化 failure_code
    a = fetch_assessment(engine, aid)
    assert a["status"] == "failed" and a["failure_code"] == "DEPENDENCY_UNAVAILABLE"


def test_analyze_terminal_failed_different_rev_noop(
    engine: Engine, tmp_path: Any
) -> None:
    """不同输入代次的终态：保持 stale no-op（T12 succeeded，T05 不变）。"""
    aid = seed_assessment(
        engine, status="failed", current_photo_version=1, processing_revision=3
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET failure_code='DEPENDENCY_UNAVAILABLE'"
                " WHERE id=CAST(:id AS uuid)"
            ),
            {"id": aid},
        )
    jid = _enqueue_analyze(engine, aid, 2)
    status, exc, _ = run_claimed(
        engine, analyze_handler, jid,
        extras=_extras(FilesystemStorageDouble(tmp_path / "s"), FaceDouble()),
    )
    assert status == "succeeded" and exc is None
    assert fetch_job(engine, jid)["status"] == "succeeded"
    assert fetch_assessment(engine, aid)["status"] == "failed"


# ---------------------- BLOCKER 4 / IMPORTANT 6：源图读取配置错误 → 终态 ----------


class _RaisingReadStorage:
    """包装替身：``get`` 记录调用次数后抛指定异常（不发起真实对象读取）。"""

    def __init__(self, inner: FilesystemStorageDouble, exc: BaseException) -> None:
        self._inner = inner
        self._exc = exc
        self.get_calls = 0

    def put(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        self._inner.put(object_key, data, content_type=content_type)

    def get(self, object_key: str) -> bytes:
        self.get_calls += 1
        raise self._exc

    def delete(self, object_key: str) -> None:
        self._inner.delete(object_key)

    def exists(self, object_key: str) -> bool:
        return self._inner.exists(object_key)


def test_analyze_source_read_config_error_is_terminal(engine: Engine, tmp_path: Any) -> None:
    """源图读取遇 StorageConfigError → 终态不可重试（不吞成 SOURCE_IMAGE_UNAVAILABLE）。"""
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path)
    faulty = _RaisingReadStorage(storage, StorageConfigError("injected config error"))
    jid = _enqueue_analyze(engine, aid, 2)
    status, exc, _ = run_claimed(
        engine, analyze_handler, jid, extras=_extras(faulty, FaceDouble())
    )
    assert status == "failed" and exc is not None
    assert exc.retryable is False  # 关键：不可重试
    assert exc.code == "SOURCE_IMAGE_CONFIG_ERROR"
    assert fetch_job(engine, jid)["status"] == "failed"
    a = fetch_assessment(engine, aid)
    assert a["status"] == "failed" and a["failure_code"] == "SOURCE_IMAGE_CONFIG_ERROR"
    assert faulty.get_calls >= 1  # 确实尝试了读取后才分类为配置错误


def test_analyze_source_bucket_mismatch_terminal_no_read(
    engine: Engine, tmp_path: Any
) -> None:
    """T11 源图行 bucket≠配置桶 → 终态且**未发起任何对象读取**（IMPORTANT 6）。"""
    storage, aid, _images, _ = _seed_analysis_case(engine, tmp_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE media_objects SET bucket='other-bucket-do-not-use'"
                " WHERE assessment_id=CAST(:a AS uuid) AND purpose='assessment_source'"
            ),
            {"a": aid},
        )
    # get 抛瞬时错误：若缺 bucket 校验，将被误判为可重试 SOURCE_IMAGE_UNAVAILABLE。
    faulty = _RaisingReadStorage(storage, StorageTransientError("would be retryable"))
    jid = _enqueue_analyze(engine, aid, 2)
    status, exc, _ = run_claimed(
        engine, analyze_handler, jid, extras=_extras(faulty, FaceDouble())
    )
    assert status == "failed" and exc is not None
    assert exc.retryable is False
    assert exc.code == "SOURCE_IMAGE_CONFIG_ERROR"
    assert faulty.get_calls == 0  # 校验在读取之前，未发起任何对象读取
    assert fetch_job(engine, jid)["status"] == "failed"

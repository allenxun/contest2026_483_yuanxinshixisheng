"""``identity.enroll`` handler 覆盖：建档、幂等复用、陈旧输入、对账、槽占用。"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from conftest import enqueue, fetch_job
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    count_grants,
    count_members,
    derived_candidate,
    derived_namespace_owner,
    enroll_payload,
    fetch_assessment,
    fetch_members,
    make_ctx,
    photo_versions_for,
    run_claimed,
    seed_assessment,
    seed_source_media,
)
from mvp_worker.handlers.dshared.providers import FaceDouble
from mvp_worker.handlers.identity_enroll import handler as enroll_handler
from mvp_worker.media.storage import FilesystemStorageDouble
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import complete_success
from mvp_worker.runtime.expire import release_claim


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


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


def _seed_enroll_case(
    engine: Engine, tmp_path: Any, *, status: str = "analyzing", rev: int = 2, pv: int = 1
) -> tuple[Any, str, dict[str, str]]:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(
        engine, status=status, current_photo_version=pv, processing_revision=rev
    )
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=pv)
    _attach_photo_versions(engine, aid, pv, images)
    return storage, aid, images


def _enqueue_enroll(
    engine: Engine,
    aid: str,
    rev: int,
    pv: int,
    images: dict[str, str],
    *,
    max_attempts: int = 5,
    dedup_key: str | None = None,
    correlation_id: str | None = None,
) -> tuple[str, str]:
    corr = correlation_id or str(uuid.uuid4())
    payload = enroll_payload(
        assessment_id=aid,
        processing_revision=rev,
        photo_version=pv,
        images=images,
        correlation_id=corr,
    )
    jid, _ = enqueue(
        engine,
        job_type="identity.enroll",
        dedup_key=dedup_key or f"identity:{DEFAULT_NS}:{uuid.uuid4()}",
        owner_type="identity_namespace",
        owner_id=derived_namespace_owner(DEFAULT_NS),
        input_revision=rev,
        payload=payload,
        max_attempts=max_attempts,
    )
    return jid, corr


def test_enroll_happy_creates_member_and_links(engine: Engine, tmp_path: Any) -> None:
    storage, aid, images = _seed_enroll_case(engine, tmp_path)
    jid, corr = _enqueue_enroll(engine, aid, 2, 1, images)
    face = FaceDouble()

    status, exc, _ = run_claimed(
        engine, enroll_handler, jid, extras={"storage": storage, "face_port": face}
    )
    assert status == "succeeded" and exc is None

    assert count_members(engine, ns=DEFAULT_NS) == 1
    members = fetch_members(engine, ns=DEFAULT_NS)
    member = members[0]
    assert member["face_subject_ref"] == derived_candidate(DEFAULT_NS, aid)
    assert str(member["created_from_assessment_id"]) == aid
    enrollment = member["identity_summary"]["enrollment"]
    assert enrollment["correlation_id"] == corr
    assert enrollment["provider_config_revision"] == "1"
    assert enrollment["source_assessment_id"] == aid
    assert enrollment["photo_version"] == 1
    assert set(member["identity_summary"]["reference_media"]) == {"front", "left", "right"}

    a = fetch_assessment(engine, aid)
    assert str(a["member_id"]) == str(member["id"])
    assert a["identity_result"]["phase"] == "enrolled"
    assert a["identity_result"]["member_id"] == str(member["id"])
    assert fetch_job(engine, jid)["status"] == "succeeded"
    assert count_grants(engine) == 0  # never writes T02


def test_enroll_rerun_reuses_existing_member(engine: Engine, tmp_path: Any) -> None:
    storage, aid, images = _seed_enroll_case(engine, tmp_path)
    jid, corr = _enqueue_enroll(engine, aid, 2, 1, images)
    face = FaceDouble()
    status, _exc, _ = run_claimed(
        engine, enroll_handler, jid, extras={"storage": storage, "face_port": face}
    )
    assert status == "succeeded"
    first_member = fetch_members(engine, ns=DEFAULT_NS)[0]["id"]

    # reclaim/re-run with a different job row, same deterministic candidate
    jid2, _corr2 = _enqueue_enroll(
        engine, aid, 2, 1, images, dedup_key=f"identity:{DEFAULT_NS}:rerun"
    )
    status2, exc2, _ = run_claimed(
        engine, enroll_handler, jid2, extras={"storage": storage, "face_port": face}
    )
    assert status2 == "succeeded" and exc2 is None
    assert count_members(engine, ns=DEFAULT_NS) == 1
    assert str(fetch_members(engine, ns=DEFAULT_NS)[0]["id"]) == str(first_member)
    assert str(fetch_assessment(engine, aid)["member_id"]) == str(first_member)
    assert count_grants(engine) == 0


def test_enroll_stale_input_no_provider_call(engine: Engine, tmp_path: Any) -> None:
    storage, aid, images = _seed_enroll_case(engine, tmp_path)
    jid, _corr = _enqueue_enroll(engine, aid, 2, 1, images)
    # simulate a retake bumping revision + photo version before enrollment runs
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET processing_revision = 3,"
                " current_photo_version = 2 WHERE id = CAST(:id AS uuid)"
            ),
            {"id": aid},
        )
    face = FaceDouble()
    status, exc, _ = run_claimed(
        engine, enroll_handler, jid, extras={"storage": storage, "face_port": face}
    )
    assert status == "succeeded" and exc is None
    assert face.calls.get("register_person", 0) == 0
    assert count_members(engine, ns=DEFAULT_NS) == 0
    a = fetch_assessment(engine, aid)
    assert a["member_id"] is None
    assert fetch_job(engine, jid)["status"] == "succeeded"


def test_enroll_timeout_then_reconcile(engine: Engine, tmp_path: Any) -> None:
    storage, aid, images = _seed_enroll_case(engine, tmp_path)
    jid, _corr = _enqueue_enroll(engine, aid, 2, 1, images)
    face = FaceDouble(register="timeout", query="registered")
    status, exc, _ = run_claimed(
        engine, enroll_handler, jid, extras={"storage": storage, "face_port": face}
    )
    assert status == "succeeded" and exc is None
    assert face.calls.get("register_person", 0) == 1
    assert face.calls.get("query_registration", 0) == 1
    assert count_members(engine, ns=DEFAULT_NS) == 1
    assert fetch_assessment(engine, aid)["member_id"] is not None


def test_enroll_link_guard_rejects_after_concurrent_retake(
    engine: Engine, tmp_path: Any
) -> None:
    """B2：外部登记成功后，并发 analyze 重试已把 T05 带离登记窗口（needs_retake）。

    成员行保留（外部登记真实），但**不得归属**：T05.member_id 仍 NULL、identity_result
    不被 link 覆盖，任务仍 succeeded。缺失的成员归属由重搜的 enrolled_reconciled
    发布路径在补拍后补上（候选按 assessment 确定性派生）。
    """
    storage, aid, images = _seed_enroll_case(engine, tmp_path, status="analyzing", rev=2, pv=1)
    jid, _corr = _enqueue_enroll(engine, aid, 2, 1, images)
    face = FaceDouble()

    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=50)
    claim = next(c for c in claims if c.id == jid)
    for other in claims:
        if other.id != jid:
            release_claim(engine, other, worker_id="w-d")
    enroll_handler.validate(claim.payload)
    ctx = make_ctx(engine, claim, extras={"storage": storage, "face_port": face})
    result = enroll_handler.handle(ctx, claim)
    assert result is not None  # 外部登记已完成，返回归属 business_tx

    # 并发 analyze 重试写 needs_retake（uncertain）发生在 link 之前
    uncertain = {
        "schema_version": 1,
        "classification": "uncertain",
        "quality": {"status": "needs_retake", "required_views": ["front"]},
        "detail": "identity result uncertain",
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET status='needs_retake',"
                " identity_result=CAST(:ir AS jsonb) WHERE id=CAST(:id AS uuid)"
            ),
            {"ir": json.dumps(uncertain), "id": aid},
        )

    complete_success(engine, claim, handler_result_tx=result.business_tx)

    assert fetch_job(engine, jid)["status"] == "succeeded"
    # 成员已建（外部登记真实），但未归属
    assert count_members(engine, ns=DEFAULT_NS, ref=derived_candidate(DEFAULT_NS, aid)) == 1
    a = fetch_assessment(engine, aid)
    assert a["member_id"] is None
    assert a["status"] == "needs_retake"
    assert a["identity_result"]["classification"] == "uncertain"  # link 未覆盖


def test_enroll_unrecoverable_failure_keeps_slot(engine: Engine, tmp_path: Any) -> None:
    storage, aid, images = _seed_enroll_case(engine, tmp_path)
    jid, _corr = _enqueue_enroll(engine, aid, 2, 1, images, max_attempts=1)
    face = FaceDouble(register="failed")
    status, exc, _ = run_claimed(
        engine, enroll_handler, jid, extras={"storage": storage, "face_port": face}
    )
    assert status == "failed" and exc is not None
    assert exc.retryable is False
    assert count_members(engine, ns=DEFAULT_NS) == 0
    assert fetch_assessment(engine, aid)["member_id"] is None
    assert count_grants(engine) == 0

    # slot remains occupied: another enroll for the same namespace owner conflicts
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO async_jobs (job_type, dedup_key, owner_type, owner_id,"
                    " input_revision, payload, status, available_at, attempt_count, max_attempts)"
                    " VALUES ('identity.enroll', :k, 'identity_namespace',"
                    " CAST(:o AS uuid), 2, CAST(:p AS jsonb), 'queued',"
                    " CURRENT_TIMESTAMP, 0, 5)"
                ),
                {
                    "k": f"identity:{DEFAULT_NS}:another",
                    "o": derived_namespace_owner(DEFAULT_NS),
                    "p": json.dumps({"schema_version": 1}),
                },
            )

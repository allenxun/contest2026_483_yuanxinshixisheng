"""完成/失败写回：代次守卫、退避重排、上限耗尽、不可重试直败。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import (
    StaleGeneration,
    backoff_seconds,
    complete_failure,
    complete_success,
)

_INSERT_MEDIA = text(
    """
INSERT INTO media_objects (id, bucket, object_key, purpose, state)
VALUES (CAST(:id AS uuid), 'mvp-a-test', :object_key, 'assessment_result', 'pending')
"""
)


def _claim_one(engine: Engine, **kw: Any) -> tuple[Any, str]:
    jid, _ = enqueue(engine, **kw)
    claims = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    assert len(claims) == 1
    return claims[0], jid


def test_complete_success_publishes_and_matches_generation(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    complete_success(engine, claim)
    row = fetch_job(engine, jid)
    assert row["status"] == "succeeded"
    assert row["finished_at"] is not None
    assert row["last_error"] is None
    assert int(row["lease_revision"]) == claim.lease_revision
    # 二次提交（同代次，status 已非 running）→ 守卫拒绝
    try:
        complete_success(engine, claim)
        raise AssertionError("expected StaleGeneration on double complete")
    except StaleGeneration:
        pass


def test_complete_success_runs_business_tx_in_same_tx(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    media_id = "88888888-8888-4888-8888-888888888888"

    def business_tx(conn) -> None:
        conn.execute(
            _INSERT_MEDIA, {"id": media_id, "object_key": f"test/ok/{media_id}"}
        )

    complete_success(engine, claim, handler_result_tx=business_tx)
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM media_objects WHERE id = CAST(:id AS uuid)"),
            {"id": media_id},
        ).scalar_one()
    assert n == 1
    assert fetch_job(engine, jid)["status"] == "succeeded"


def test_retryable_failure_requeues_with_backoff(engine: Engine) -> None:
    claim, jid = _claim_one(engine)  # attempt_count=1, max=5
    complete_failure(
        engine, claim, code="DEPENDENCY_TIMEOUT", message="provider 5xx",
        retryable=True, backoff_base_seconds=5, backoff_cap_seconds=300,
    )
    row = fetch_job(engine, jid)
    assert row["status"] == "queued"
    assert row["lease_owner"] is None
    now = datetime.now(timezone.utc)
    delta = (row["available_at"] - now).total_seconds()
    # base*2^(1-1)=5s + 抖动 ≤20% → [5, 6] 秒（容忍 1s 时钟/取整误差）
    assert 4.0 <= delta <= 7.0, f"available_at 退避异常: {delta}"
    err = row["last_error"]
    assert err["code"] == "DEPENDENCY_TIMEOUT"
    assert err["retryable"] is True
    assert isinstance(err["retry_after_seconds"], int)
    assert err["message"] == "provider 5xx"
    assert set(err) <= {"code", "message", "retryable", "retry_after_seconds"}


def test_attempts_exhausted_marks_failed(engine: Engine) -> None:
    claim, jid = _claim_one(engine, max_attempts=1)  # claim 后 attempt=1=max
    complete_failure(
        engine, claim, code="DEPENDENCY_TIMEOUT", message="last try",
        retryable=True, backoff_base_seconds=5, backoff_cap_seconds=300,
    )
    row = fetch_job(engine, jid)
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert row["last_error"]["retryable"] is False  # 终态不再宣称可重试
    assert "retry_after_seconds" not in row["last_error"]


def test_non_retryable_failure_fails_immediately(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    complete_failure(
        engine, claim, code="FACE_QUALITY_REJECTED", message="quality",
        retryable=False,
    )
    row = fetch_job(engine, jid)
    assert row["status"] == "failed"
    assert row["last_error"]["code"] == "FACE_QUALITY_REJECTED"
    assert row["last_error"]["retryable"] is False


def test_failure_write_with_stale_generation_raises(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET lease_revision = lease_revision + 1 "
                 "WHERE id = :id"),
            {"id": jid},
        )
    try:
        complete_failure(engine, claim, code="X", message="m", retryable=True)
        raise AssertionError("expected StaleGeneration")
    except StaleGeneration:
        pass


def test_failure_business_tx_commits_atomically_with_failed(engine: Engine) -> None:
    """N2：终态业务写随 complete_failure 同一事务原子提交（T05/T06 failed + T12 failed）。"""
    claim, jid = _claim_one(engine)
    media_id = "b1b1b1b1-b1b1-4b1b-8b1b-b1b1b1b1b1b1"

    def business_tx(conn: Any) -> None:
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"test/fail/{media_id}"})

    complete_failure(
        engine, claim, code="FACE_QUALITY_REJECTED", message="q",
        retryable=False, business_tx=business_tx,
    )
    assert fetch_job(engine, jid)["status"] == "failed"
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM media_objects WHERE id = CAST(:id AS uuid)"),
            {"id": media_id},
        ).scalar_one()
    assert int(n) == 1


def test_failure_business_tx_error_rolls_back_business_and_job(engine: Engine) -> None:
    """N2：业务回调抛错 → 业务写与任务状态整体回滚（job 仍 running/同代次）。"""
    claim, jid = _claim_one(engine)
    media_id = "b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2"

    def bad(conn: Any) -> None:
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"test/bad/{media_id}"})
        raise RuntimeError("callback exploded")

    with pytest.raises(RuntimeError):
        complete_failure(
            engine, claim, code="X", message="m", retryable=False, business_tx=bad
        )
    row = fetch_job(engine, jid)
    assert row["status"] == "running"  # 任务状态未改
    assert row["lease_owner"] == claim.lease_owner
    assert int(row["lease_revision"]) == claim.lease_revision
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM media_objects WHERE id = CAST(:id AS uuid)"),
            {"id": media_id},
        ).scalar_one()
    assert int(n) == 0  # 业务写回滚


def test_failure_expired_lease_rejects_business_and_job(engine: Engine) -> None:
    """N2：租约过期 → 业务与任务状态双拒（StaleGeneration，整体无变化）。"""
    claim, jid = _claim_one(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP"
                " - make_interval(secs => 5) WHERE id = :id"
            ),
            {"id": jid},
        )
    media_id = "b3b3b3b3-b3b3-4b3b-8b3b-b3b3b3b3b3b3"

    def business_tx(conn: Any) -> None:
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"test/exp/{media_id}"})

    with pytest.raises(StaleGeneration):
        complete_failure(
            engine, claim, code="X", message="m", retryable=False, business_tx=business_tx
        )
    row = fetch_job(engine, jid)
    assert row["status"] == "running"  # 任务未改
    assert int(row["lease_revision"]) == claim.lease_revision
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM media_objects WHERE id = CAST(:id AS uuid)"),
            {"id": media_id},
        ).scalar_one()
    assert int(n) == 0  # 业务未提交


def test_failure_callback_respects_attempt_budget_on_requeue(engine: Engine) -> None:
    """N2：带回调的可重试失败仍沿原 attempt 预算（attempt=1<5 → requeue 不退还）。"""
    claim, jid = _claim_one(engine, max_attempts=5)
    calls: list[int] = []

    def business_tx(conn: Any) -> None:
        calls.append(1)

    complete_failure(
        engine, claim, code="DEPENDENCY_TIMEOUT", message="m", retryable=True,
        backoff_base_seconds=0, backoff_cap_seconds=0, business_tx=business_tx,
    )
    row = fetch_job(engine, jid)
    assert row["status"] == "queued"
    assert int(row["attempt_count"]) == claim.attempt_count == 1  # 不退还/不额外
    assert calls == [1]


def test_backoff_formula_exponential_capped():
    import random

    rng = random.Random(7)
    d1 = backoff_seconds(1, base_seconds=5, cap_seconds=300, rng=rng)
    d5 = backoff_seconds(5, base_seconds=5, cap_seconds=300, rng=rng)
    d20 = backoff_seconds(20, base_seconds=5, cap_seconds=300, rng=rng)
    assert 5 <= d1 <= 6  # 5 + ≤20%
    assert 80 <= d5 <= 96  # 5*2^4=80 + ≤20%
    assert 300 <= d20 <= 360  # 封顶 300 + ≤20%

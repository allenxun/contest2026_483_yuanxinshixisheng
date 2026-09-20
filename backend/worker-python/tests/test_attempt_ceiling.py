"""T12 重试上限（oracle M7）：崩溃/租约过期循环不得突破 max_attempts。

- 领取条件含 attempt_count < max_attempts：已触顶的 queued 行永不再被领取；
- 过期回收：有预算 → 重排队（代次+1）；触顶 → failed 终态
  （last_error.code=RETRY_LIMIT_EXCEEDED，attempt_count 不再增长）；
- 优雅停机释放同样不制造"触顶 queued 滞留"：触顶即 failed。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.expire import recover_expired, release_claim


def _expire_lease(engine: Engine, jid: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP - interval '1 second'"
                 " WHERE id = :id"),
            {"id": jid},
        )


def test_crash_loop_stops_at_ceiling(engine: Engine) -> None:
    """max_attempts=1：claim→崩溃→过期回收 必须落 failed（不再重排队）。"""
    jid, _ = enqueue(engine, max_attempts=1)
    claims = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.attempt_count == 1 and claim.max_attempts == 1

    _expire_lease(engine, jid)  # 模拟 worker 崩溃，租约到期
    assert recover_expired(engine) == 1
    row = fetch_job(engine, jid)
    assert row["status"] == "failed"
    assert int(row["attempt_count"]) == 1, "触顶回收不得增加 attempt_count"
    assert row["finished_at"] is not None
    err = row["last_error"]
    if isinstance(err, str):
        import json
        err = json.loads(err)
    assert err["code"] == "RETRY_LIMIT_EXCEEDED"
    assert err["retryable"] is False
    # 幂等：再回收 0
    assert recover_expired(engine) == 0


def test_queued_at_ceiling_never_claimed(engine: Engine) -> None:
    """已触顶的 queued 行（attempt_count >= max_attempts）不被领取。"""
    jid, _ = enqueue(engine, max_attempts=3)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET attempt_count = 3 WHERE id = :id"), {"id": jid}
        )
    assert claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5) == []
    row = fetch_job(engine, jid)
    assert row["status"] == "queued", "领取器不改写行——等待恢复器/人工处置"


def test_recover_keeps_budget_rows_requeued(engine: Engine) -> None:
    """未触顶的过期行照旧重排队 + 代次 +1（既有行为回归）。"""
    jid, _ = enqueue(engine, max_attempts=2)
    claims = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    before = fetch_job(engine, jid)
    _expire_lease(engine, jid)
    assert recover_expired(engine) == 1
    after = fetch_job(engine, jid)
    assert after["status"] == "queued"
    assert int(after["lease_revision"]) == int(before["lease_revision"]) + 1
    assert int(after["attempt_count"]) == 1 < 2


def test_graceful_release_at_ceiling_fails_row(engine: Engine) -> None:
    """停机释放触顶行：不得回到 queued 滞留，直接 failed。"""
    jid, _ = enqueue(engine, max_attempts=1)
    claims = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    claim: Any = claims[0]
    assert release_claim(engine, claim, worker_id="w1") is True
    row = fetch_job(engine, jid)
    assert row["status"] == "failed"
    assert int(row["attempt_count"]) == 1

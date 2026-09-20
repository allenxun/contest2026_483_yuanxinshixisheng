"""``complete_deferred``：合法等待态重排、attempt 退还、代次/租约围栏、业务守卫回滚。

对应 A1/A3/A5：defer 只用于合法等待态；真实失败仍走 complete_failure 并消耗
attempt。所有守卫 0 行 → StaleGeneration（事务整体回滚，无 refund）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from mvp_worker.config import WorkerConfig
from mvp_worker.handlers import HandlerResult
from mvp_worker.runtime import loop as loop_module
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import (
    StaleGeneration,
    complete_deferred,
    complete_failure,
)
from mvp_worker.runtime.loop import WorkerRuntime

_INSERT_MEDIA = text(
    """
INSERT INTO media_objects (id, bucket, object_key, purpose, state)
VALUES (CAST(:id AS uuid), 'mvp-d-defer-test', :object_key, 'assessment_result', 'pending')
"""
)


def _claim_one(engine: Engine, **kw: Any) -> tuple[Any, str]:
    jid, _ = enqueue(engine, **kw)
    claims = claim_batch(engine, worker_id="w-defer", lease_seconds=60, batch_size=5)
    assert len(claims) == 1
    return claims[0], jid


def test_defer_requeues_same_job_refunds_attempt(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    base = fetch_job(engine, jid)
    assert int(base["attempt_count"]) == 1  # claim 已 +1

    complete_deferred(engine, claim, defer_seconds=42)
    row = fetch_job(engine, jid)
    assert row["status"] == "queued"
    assert row["lease_owner"] is None and row["lease_until"] is None
    assert int(row["attempt_count"]) == 0  # 退还本次 claim 增量 → 回到 pre-claim
    assert int(row["lease_revision"]) == claim.lease_revision + 1  # 作废旧代次
    assert str(row["id"]) == jid  # 同一 job，不产生后继
    assert row["dedup_key"] == base["dedup_key"]
    assert row["last_error"] is None  # defer 不写诊断字段
    delta = (row["available_at"] - datetime.now(timezone.utc)).total_seconds()
    assert 38.0 <= delta <= 46.0, f"available_at 未按 defer 推进: {delta}"


def test_defer_three_cycles_preserve_budget_identity_and_available_at(engine: Engine) -> None:
    """(a) runtime 级：连续 ≥3 次 claim→defer 不烧预算、同一 job/dedup、available_at 前移。"""
    jid, _ = enqueue(engine)
    baseline = fetch_job(engine, jid)
    baseline_attempts = int(baseline["attempt_count"])
    assert baseline_attempts == 0  # pre-first-claim 基线
    prev_available = baseline["available_at"]
    prev_revision = int(baseline["lease_revision"])

    for _ in range(3):
        claims = claim_batch(engine, worker_id="w-defer", lease_seconds=60, batch_size=5)
        assert len(claims) == 1
        claim = claims[0]
        assert claim.id == jid  # 同一 job，绝不产生后继
        assert int(claim.attempt_count) == 1  # 本次 claim +1
        assert int(claim.lease_revision) == prev_revision + 1  # claim 提升代次
        complete_deferred(engine, claim, defer_seconds=0)
        row = fetch_job(engine, jid)
        assert row["status"] == "queued"
        assert str(row["id"]) == jid
        assert row["dedup_key"] == baseline["dedup_key"]  # 身份不变
        assert row["lease_owner"] is None and row["lease_until"] is None  # 租约清空
        assert int(row["attempt_count"]) == baseline_attempts  # 退还本次增量
        assert int(row["lease_revision"]) == int(claim.lease_revision) + 1  # 作废旧代次
        assert row["available_at"] > prev_available  # available_at 每次前移
        assert row["last_error"] is None  # 诊断字段不参与 defer
        prev_available = row["available_at"]
        prev_revision = int(row["lease_revision"])


def test_defer_business_tx_stale_rolls_back_everything(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    media_id = "77777777-7777-4777-8777-777777777777"

    def guard(conn: Any) -> None:
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"test/{media_id}"})
        raise StaleGeneration("business input changed since claim")

    try:
        complete_deferred(engine, claim, defer_seconds=30, business_tx=guard)
        raise AssertionError("expected StaleGeneration")
    except StaleGeneration:
        pass

    row = fetch_job(engine, jid)
    assert row["status"] == "running"  # 未重排
    assert row["lease_owner"] == claim.lease_owner  # 仍持有租约
    assert int(row["attempt_count"]) == claim.attempt_count  # 未退款
    assert int(row["lease_revision"]) == claim.lease_revision  # 未提升代次
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM media_objects WHERE id = CAST(:id AS uuid)"),
            {"id": media_id},
        ).scalar_one()
    assert int(n) == 0  # 业务写随 defer 一起回滚


def test_defer_expired_lease_stale_no_change(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP"
                " - make_interval(secs => 5) WHERE id = :id"
            ),
            {"id": jid},
        )
    try:
        complete_deferred(engine, claim, defer_seconds=10)
        raise AssertionError("expected StaleGeneration on expired lease")
    except StaleGeneration:
        pass
    row = fetch_job(engine, jid)
    assert row["status"] == "running"
    assert row["lease_owner"] == claim.lease_owner
    assert int(row["attempt_count"]) == claim.attempt_count  # no refund
    assert int(row["lease_revision"]) == claim.lease_revision  # no state change


def test_defer_bumped_revision_stale_no_change(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET lease_revision = lease_revision + 1 WHERE id = :id"),
            {"id": jid},
        )
    try:
        complete_deferred(engine, claim, defer_seconds=10)
        raise AssertionError("expected StaleGeneration on bumped revision")
    except StaleGeneration:
        pass
    row = fetch_job(engine, jid)
    assert row["status"] == "running"
    assert int(row["attempt_count"]) == claim.attempt_count  # no refund
    assert int(row["lease_revision"]) == claim.lease_revision + 1  # untouched by defer


def test_defer_duplicate_second_fails_no_double_refund(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    complete_deferred(engine, claim, defer_seconds=1)
    first = fetch_job(engine, jid)
    assert int(first["attempt_count"]) == 0
    assert int(first["lease_revision"]) == claim.lease_revision + 1

    try:
        complete_deferred(engine, claim, defer_seconds=1)
        raise AssertionError("expected StaleGeneration on duplicate defer")
    except StaleGeneration:
        pass
    second = fetch_job(engine, jid)
    assert second["status"] == "queued"
    assert int(second["attempt_count"]) == 0  # 无二次退款/不负数
    assert int(second["lease_revision"]) == first["lease_revision"]


def test_complete_failure_still_consumes_attempt(engine: Engine) -> None:
    claim, jid = _claim_one(engine, max_attempts=5)
    complete_failure(engine, claim, code="DEPENDENCY_TIMEOUT", message="boom", retryable=True)
    row = fetch_job(engine, jid)
    assert row["status"] == "queued"
    assert int(row["attempt_count"]) == claim.attempt_count == 1  # 真失败不退还
    assert row["last_error"]["code"] == "DEPENDENCY_TIMEOUT"


class _DeferStubHandler:
    """测试用 handler：validate 恒过，handle 返回固定 defer。"""

    name = "defer-stub"

    def validate(self, payload: Any) -> None:
        return None

    def handle(self, ctx: Any, job: Any) -> HandlerResult:
        return HandlerResult(defer_seconds=17)


def test_loop_process_job_dispatches_defer(engine: Engine, monkeypatch: Any) -> None:
    """A3：WorkerRuntime.process_job 对 HandlerResult.defer_seconds 走 complete_deferred。"""
    jid, _ = enqueue(engine, max_attempts=5)
    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=5)
    claim = next(c for c in claims if c.id == jid)

    monkeypatch.setattr(loop_module, "get_handler", lambda _jt: _DeferStubHandler())
    runtime = WorkerRuntime(WorkerConfig(runtime_dsn="unused"), engine=engine)
    runtime.process_job(claim)

    row = fetch_job(engine, jid)
    assert row["status"] == "queued"  # 重排而非 succeeded
    assert row["lease_owner"] is None
    assert int(row["attempt_count"]) == 0  # 退款
    assert int(row["lease_revision"]) == claim.lease_revision + 1
    delta = (row["available_at"] - datetime.now(timezone.utc)).total_seconds()
    assert 14.0 <= delta <= 19.0

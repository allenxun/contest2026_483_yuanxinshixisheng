"""Ruling §271.2：租约有效性必须用 ``clock_timestamp()``（真实执行时刻）。

``complete_failure`` / ``complete_deferred`` 的业务回调在守卫 UPDATE **之前**执行；
若回调耗时耗尽租约，守卫必须在**此刻**判过期 → ``StaleGeneration`` → 业务 + 任务写
整体回滚（过期领取者绝不提交结果）。旧的事务起始 ``CURRENT_TIMESTAMP`` 语义下，这些
mid-transaction 用例会在租约仍「活跃」时误提交——故本文件是本次修复的回归证据。
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from mvp_worker.handlers.dshared.dfence import fenced_business_tx
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import (
    StaleGeneration,
    complete_deferred,
    complete_failure,
    complete_success,
)

_INSERT_MEDIA = text(
    """
INSERT INTO media_objects (id, bucket, object_key, purpose, state)
VALUES (CAST(:id AS uuid), 'mvp-lease-clock', :object_key, 'assessment_result', 'pending')
"""
)


def _claim_one(
    engine: Engine, *, lease_seconds: int = 60, max_attempts: int = 5
) -> tuple[Any, str]:
    jid, _ = enqueue(engine, max_attempts=max_attempts)
    claims = claim_batch(
        engine, worker_id="w-d", lease_seconds=lease_seconds, batch_size=5
    )
    assert len(claims) == 1
    return claims[0], jid


def _set_lease_in(engine: Engine, jid: str, seconds: float) -> None:
    """把租约设为 ``clock_timestamp() + seconds``（墙钟语义；负值=已过期未回收）。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE async_jobs SET lease_until = clock_timestamp()"
                " + make_interval(secs => :s) WHERE id = :id"
            ),
            {"s": float(seconds), "id": jid},
        )


def _media_count(engine: Engine, media_id: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM media_objects WHERE id = CAST(:id AS uuid)"),
                {"id": media_id},
            ).scalar_one()
        )


def test_complete_failure_mid_tx_expiry_rejects_and_rolls_back(engine: Engine) -> None:
    """(a) 回调耗尽租约 → complete_failure 守卫此刻判过期 → 业务回滚、job 不变。

    旧 ``CURRENT_TIMESTAMP`` 语义（事务起始冻结）下守卫会看到租约尚活跃 → 误提交，
    故本测试在该语义下会失败（这正是修复点）。
    """
    claim, jid = _claim_one(engine)
    before = fetch_job(engine, jid)
    _set_lease_in(engine, jid, 0.3)  # 0.3s 后过期
    media_id = str(uuid.uuid4())

    def business_tx(conn: Any) -> None:
        # 先执行 SQL（确定服务端事务起始时间戳），再睡过租约：旧 CURRENT_TIMESTAMP
        # 语义下守卫会用此 SQL 建立的事务起始时间（租约尚活）→ 误提交；clock_timestamp()
        # 则在守卫真实执行时判过期 → 拒绝。故本测试对两种语义具判别力。
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"t/{media_id}"})
        time.sleep(0.9)  # 耗尽租约（≥0.5s 余量）

    with pytest.raises(StaleGeneration):
        complete_failure(
            engine, claim, code="X", message="m", retryable=False, business_tx=business_tx
        )

    row = fetch_job(engine, jid)
    assert row["status"] == "running"
    assert row["lease_owner"] == before["lease_owner"]
    assert int(row["lease_revision"]) == int(before["lease_revision"])
    assert row["last_error"] is None
    assert _media_count(engine, media_id) == 0  # 业务写回滚


def test_complete_deferred_mid_tx_expiry_rejects_no_refund(engine: Engine) -> None:
    """(b) 回调耗尽租约 → complete_deferred 守卫判过期 → 不重排、attempt 不退还、业务回滚。"""
    claim, jid = _claim_one(engine)
    before = fetch_job(engine, jid)
    attempts_before = int(before["attempt_count"])
    _set_lease_in(engine, jid, 0.3)
    media_id = str(uuid.uuid4())

    def business_tx(conn: Any) -> None:
        # 先 SQL 建立事务时间戳，再睡过租约（判别力同上）。
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"t/{media_id}"})
        time.sleep(0.9)

    with pytest.raises(StaleGeneration):
        complete_deferred(engine, claim, defer_seconds=5, business_tx=business_tx)

    row = fetch_job(engine, jid)
    assert row["status"] == "running"
    assert row["lease_owner"] == before["lease_owner"]
    assert int(row["attempt_count"]) == attempts_before  # 未退款
    assert int(row["lease_revision"]) == int(before["lease_revision"])  # 未提升代次
    assert _media_count(engine, media_id) == 0


def test_dfence_expired_lease_rejects_no_write(engine: Engine) -> None:
    """(c) fenced_business_tx：已过期（未回收）租约 → StaleGeneration，无业务写。"""
    claim, jid = _claim_one(engine)
    _set_lease_in(engine, jid, -5)
    media_id = str(uuid.uuid4())

    with pytest.raises(StaleGeneration):
        with fenced_business_tx(engine, claim) as conn:
            conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"t/{media_id}"})

    assert _media_count(engine, media_id) == 0
    assert fetch_job(engine, jid)["status"] == "running"


def test_complete_failure_generous_lease_commits(engine: Engine) -> None:
    """(d) 对照：充足租约 + 回调 0.3s → 正常终态失败且业务写提交。"""
    claim, jid = _claim_one(engine, lease_seconds=60)
    media_id = str(uuid.uuid4())

    def business_tx(conn: Any) -> None:
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"t/{media_id}"})
        time.sleep(0.3)

    complete_failure(
        engine, claim, code="X", message="m", retryable=False, business_tx=business_tx
    )
    assert fetch_job(engine, jid)["status"] == "failed"
    assert _media_count(engine, media_id) == 1


# --------------------------------------- (A) complete_success live-lease guard


def test_complete_success_mid_tx_expiry_rejected_and_rolls_back(engine: Engine) -> None:
    """(A) 成功路径：回调耗尽租约 → 守卫（clock_timestamp）拒绝 → 业务 + succeeded 回滚。"""
    claim, jid = _claim_one(engine)
    before = fetch_job(engine, jid)
    _set_lease_in(engine, jid, 0.3)  # 0.3s 后过期
    media_id = str(uuid.uuid4())

    def business_tx(conn: Any) -> None:
        # 先 SQL（建立服务端事务时间戳），再睡过租约：旧 CURRENT_TIMESTAMP 语义会
        # 用事务起始（租约尚活）→ 误提交 succeeded；clock_timestamp() 判过期 → 拒绝。
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"t/{media_id}"})
        time.sleep(0.9)  # ≥0.5s 余量

    with pytest.raises(StaleGeneration):
        complete_success(engine, claim, handler_result_tx=business_tx)

    row = fetch_job(engine, jid)
    assert row["status"] == "running"  # 未 succeeded
    assert row["lease_owner"] == before["lease_owner"]
    assert int(row["lease_revision"]) == int(before["lease_revision"])
    assert _media_count(engine, media_id) == 0  # 业务写回滚


def test_complete_success_generous_lease_commits(engine: Engine) -> None:
    """(A) 对照：充足租约 + 0.3s 回调 → succeeded 且业务写提交。"""
    claim, jid = _claim_one(engine, lease_seconds=60)
    media_id = str(uuid.uuid4())

    def business_tx(conn: Any) -> None:
        conn.execute(_INSERT_MEDIA, {"id": media_id, "object_key": f"t/{media_id}"})
        time.sleep(0.3)

    complete_success(engine, claim, handler_result_tx=business_tx)
    assert fetch_job(engine, jid)["status"] == "succeeded"
    assert _media_count(engine, media_id) == 1


def test_no_callback_success_live_succeeds(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    complete_success(engine, claim)
    assert fetch_job(engine, jid)["status"] == "succeeded"


def test_no_callback_success_expired_is_stale(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    before = fetch_job(engine, jid)
    _set_lease_in(engine, jid, -5)
    with pytest.raises(StaleGeneration):
        complete_success(engine, claim)
    row = fetch_job(engine, jid)
    assert row["status"] == "running"
    assert int(row["attempt_count"]) == int(before["attempt_count"])
    assert int(row["lease_revision"]) == int(before["lease_revision"])


# --------------------------------------------------- (e) no-callback 兼容回归


def test_no_callback_failure_live_fails(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    complete_failure(engine, claim, code="X", message="m", retryable=False)
    assert fetch_job(engine, jid)["status"] == "failed"


def test_no_callback_failure_expired_is_stale(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    before = fetch_job(engine, jid)
    _set_lease_in(engine, jid, -5)
    with pytest.raises(StaleGeneration):
        complete_failure(engine, claim, code="X", message="m", retryable=False)
    row = fetch_job(engine, jid)
    assert row["status"] == "running"
    assert int(row["attempt_count"]) == int(before["attempt_count"])
    assert int(row["lease_revision"]) == int(before["lease_revision"])


def test_no_callback_deferred_live_requeues_and_refunds(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    complete_deferred(engine, claim, defer_seconds=5)
    row = fetch_job(engine, jid)
    assert row["status"] == "queued"
    assert int(row["attempt_count"]) == 0  # claim +1 → 退还回 pre-claim 基线
    assert int(row["lease_revision"]) == int(claim.lease_revision) + 1


def test_no_callback_deferred_expired_is_stale_no_refund(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    before = fetch_job(engine, jid)
    _set_lease_in(engine, jid, -5)
    with pytest.raises(StaleGeneration):
        complete_deferred(engine, claim, defer_seconds=5)
    row = fetch_job(engine, jid)
    assert row["status"] == "running"
    assert int(row["attempt_count"]) == int(before["attempt_count"])  # 未退款
    assert int(row["lease_revision"]) == int(before["lease_revision"])

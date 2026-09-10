"""续租：正确代次成功；错误代次/过期租约 → LostLease；看门狗协作中止。"""
from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.renew import LeaseRenewer, LostLease, renew


def _claim_one(engine: Engine) -> Any:
    enqueue(engine)
    claims = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    assert len(claims) == 1
    return claims[0]


def test_renew_extends_lease_for_correct_generation(engine: Engine) -> None:
    claim = _claim_one(engine)
    before = fetch_job(engine, claim.id)["lease_until"]
    assert renew(engine, claim.id, "w1", claim.lease_revision, lease_seconds=120)
    after = fetch_job(engine, claim.id)["lease_until"]
    assert after > before + timedelta(seconds=60)
    # 续租不改变代次
    assert int(fetch_job(engine, claim.id)["lease_revision"]) == claim.lease_revision


def test_renew_wrong_generation_raises(engine: Engine) -> None:
    claim = _claim_one(engine)
    try:
        renew(engine, claim.id, "w1", claim.lease_revision + 999, lease_seconds=60)
        raise AssertionError("expected LostLease")
    except LostLease:
        pass
    try:
        renew(engine, claim.id, "someone-else", claim.lease_revision, lease_seconds=60)
        raise AssertionError("expected LostLease for wrong owner")
    except LostLease:
        pass


def test_renew_refused_after_lease_expired(engine: Engine) -> None:
    claim = _claim_one(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP "
                 "- interval '2 seconds' WHERE id = :id"),
            {"id": claim.id},
        )
    try:
        renew(engine, claim.id, "w1", claim.lease_revision, lease_seconds=60)
        raise AssertionError("expected LostLease on expired lease")
    except LostLease:
        pass
    # 未改状态：仍 running（回收器负责转 queued）
    assert fetch_job(engine, claim.id)["status"] == "running"


def test_renewer_watchdog_sets_abort_on_lost_lease(engine: Engine) -> None:
    claim = _claim_one(engine)
    with engine.begin() as conn:  # 模拟租约即刻过期
        conn.execute(
            text("UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP - interval '1 second' "
                 "WHERE id = :id"),
            {"id": claim.id},
        )
    abort = threading.Event()
    renewer = LeaseRenewer(
        engine, claim, lease_seconds=60, renew_interval_seconds=0.2, abort_event=abort
    ).start()
    try:
        assert abort.wait(timeout=5.0), "看门狗应在 LostLease 后置位 abort"
    finally:
        renewer.stop()

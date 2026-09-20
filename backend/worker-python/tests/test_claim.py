"""领取协议：互斥、代次递增、未来 available_at 不领取。"""
from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import Engine

from conftest import enqueue, fetch_job
from mvp_worker.db import create_db_engine
from mvp_worker.runtime.claim import claim_batch


def test_claim_sets_running_and_bumps_generation(engine: Engine) -> None:
    ids = [enqueue(engine, payload={
        "schema_version": 1, "message": f"m{i}", "numbers_as_strings": ["0"],
    })[0] for i in range(3)]

    claimed = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    assert {c.id for c in claimed} == set(ids)
    for c in claimed:
        assert c.lease_revision == 1  # 新代次（UPDATE 后值）
        assert c.attempt_count == 1
        assert c.lease_owner == "w1"
        row = fetch_job(engine, c.id)
        assert row["status"] == "running"
        assert row["lease_owner"] == "w1"
        assert int(row["lease_revision"]) == 1
        assert int(row["attempt_count"]) == 1
        assert row["lease_until"] is not None


def test_future_available_at_not_claimed(engine: Engine) -> None:
    enqueue(engine, available_at_delay_seconds=3600)
    now_job, _ = enqueue(engine)
    claimed = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    assert [c.id for c in claimed] == [now_job]


def test_two_concurrent_claimers_never_share_job(test_dsn: str) -> None:
    eng_a = create_db_engine(test_dsn, pool_size=2, max_overflow=0)
    eng_b = create_db_engine(test_dsn, pool_size=2, max_overflow=0)
    try:
        ids = {enqueue(eng_a)[0] for _ in range(6)}
        results: dict[str, set[str]] = {}
        barrier = threading.Barrier(2)

        def worker(name: str, eng: Any) -> None:
            barrier.wait()
            got = claim_batch(eng, worker_id=name, lease_seconds=60, batch_size=5)
            results[name] = {c.id for c in got}

        t1 = threading.Thread(target=worker, args=("claimer-1", eng_a))
        t2 = threading.Thread(target=worker, args=("claimer-2", eng_b))
        t1.start(); t2.start(); t1.join(timeout=30); t2.join(timeout=30)
        assert set(results) == {"claimer-1", "claimer-2"}
        a, b = results["claimer-1"], results["claimer-2"]
        assert a & b == set(), f"同一任务被领取两次: {a & b}"
        assert a | b == ids  # 全部被领走（6 ≤ 2*batch）
        for jid in a:
            assert fetch_job(eng_a, jid)["lease_owner"] == "claimer-1"
        for jid in b:
            assert fetch_job(eng_a, jid)["lease_owner"] == "claimer-2"
    finally:
        eng_a.dispose()
        eng_b.dispose()

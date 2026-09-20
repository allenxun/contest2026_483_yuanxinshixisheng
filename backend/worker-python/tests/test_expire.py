"""过期回收：条件更新转回 queued + 代次失效 + 旧领取者结果整体回滚。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import StaleGeneration, complete_success
from mvp_worker.runtime.expire import recover_expired, release_claim

_INSERT_MEDIA = text(
    """
INSERT INTO media_objects (id, bucket, object_key, purpose, state)
VALUES (CAST(:id AS uuid), 'mvp-a-test', :object_key, 'assessment_result', 'pending')
"""
)


def _claim_one(engine: Engine) -> Any:
    jid, _ = enqueue(engine)
    claims = claim_batch(engine, worker_id="w1", lease_seconds=60, batch_size=5)
    return claims[0], jid


def test_recover_expired_requeues_with_generation_bump(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP - interval '1 second' "
                 "WHERE id = :id"),
            {"id": jid},
        )
    before = fetch_job(engine, jid)

    assert recover_expired(engine) == 1
    after = fetch_job(engine, jid)
    assert after["status"] == "queued"
    assert after["lease_owner"] is None
    assert after["lease_until"] is None
    assert int(after["lease_revision"]) == int(before["lease_revision"]) + 1
    assert int(after["attempt_count"]) == int(before["attempt_count"])  # 不改尝试数
    assert after["available_at"] == before["available_at"]  # 不改 available_at
    # 幂等：再次回收 0 条
    assert recover_expired(engine) == 0


def test_stale_claimer_complete_success_rolls_back_business_write(engine: Engine) -> None:
    """验收核心：回收后旧代次 complete_success 必须 StaleGeneration，
    且同事务内的业务写（media_objects，Worker 允许写的表）不得发布。"""
    claim, jid = _claim_one(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET lease_until = CURRENT_TIMESTAMP - interval '1 second' "
                 "WHERE id = :id"),
            {"id": jid},
        )
    assert recover_expired(engine) == 1

    sentinel_media_id = "77777777-7777-4777-8777-777777777777"

    def business_tx(conn) -> None:
        conn.execute(
            _INSERT_MEDIA,
            {"id": sentinel_media_id, "object_key": f"test/rollback/{sentinel_media_id}"},
        )

    try:
        complete_success(engine, claim, handler_result_tx=business_tx)
        raise AssertionError("expected StaleGeneration")
    except StaleGeneration:
        pass
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM media_objects WHERE id = CAST(:id AS uuid)"),
            {"id": sentinel_media_id},
        ).scalar_one()
    assert n == 0, "业务写必须随 stale generation 一起回滚"
    # 任务现属新代次持有者：仍可被重新领取
    # 代次轨迹：claim→1，recover→2，re-claim→3
    fresh = claim_batch(engine, worker_id="w2", lease_seconds=60, batch_size=5)
    assert [c.id for c in fresh] == [jid]
    assert fresh[0].lease_revision == 3


def test_release_claim_returns_job_and_invalidates_generation(engine: Engine) -> None:
    claim, jid = _claim_one(engine)
    assert release_claim(engine, claim, worker_id="w1") is True
    after = fetch_job(engine, jid)
    assert after["status"] == "queued"
    assert int(after["lease_revision"]) == claim.lease_revision + 1
    # 旧代次的释放/完成一律失效
    assert release_claim(engine, claim, worker_id="w1") is False

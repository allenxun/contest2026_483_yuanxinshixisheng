"""Python 必测 14：重试与退避、重试前重检、超过 max_attempts 的终态（真实 PG @55435）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Engine, text
from b_support import b_clean_tables  # noqa: F401  autouse B 自清（按 FK 顺序清 B 自己的行）
from test_notification_support import (
    claim_one,
    device_episode,
    enqueue_deliver_job,
    fetch_job,
    fetch_notification,
    run_delivery,
    seed_account,
    seed_destination,
    seed_gimbal,
    seed_notification,
)

from mvp_worker.notifications.push import DevTestDoublePushProvider
from mvp_worker.notifications.session_probe import DevDbSessionProbe
from mvp_worker.handlers.notification_deliver import NotificationDeliverHandler


def _seed_linked(engine: Engine):
    account = seed_account(engine)
    incident = str(uuid.uuid4())
    gimbal = seed_gimbal(
        engine, account_id=account, binding_revision=1, status="online",
        episodes=device_episode(incident),
    )
    dest = seed_destination(engine, account_id=account, revision=1, session_ref="sess-1")
    notification = seed_notification(
        engine, gimbal_id=gimbal, incident_id=incident, account_id=account,
        binding_revision=1, destination_id=dest, destination_revision=1,
    )
    return account, gimbal, dest, notification


def _handler(engine: Engine, provider: DevTestDoublePushProvider) -> NotificationDeliverHandler:
    return NotificationDeliverHandler(
        push_provider=provider, session_probe=DevDbSessionProbe(engine)
    )


def test_transient_requeues_with_backoff(engine: Engine) -> None:
    _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=5)
    provider = DevTestDoublePushProvider(mode="transient")
    job = claim_one(engine)
    assert job is not None

    before = datetime.now(timezone.utc)
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None and failure.retryable is True
    row = fetch_job(engine, job_id)
    assert row["status"] == "queued"
    assert row["attempt_count"] == 1
    assert row["available_at"] > before, "可重试失败必须把 available_at 推后（退避）"
    err = json.loads(row["last_error"])
    assert err["retryable"] is True
    assert err["code"] == "provider_transient"
    # 发送后崩溃窗口：T10 保持可观测 sending（下次对账）
    assert fetch_notification(engine, notification)["status"] == "sending"
    assert len(provider.calls) == 1


def test_retry_rechecks_and_cancels_after_rebind(engine: Engine) -> None:
    account, gimbal, _, notification = _seed_linked(engine)
    other = seed_account(engine)
    enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=5)
    provider = DevTestDoublePushProvider(mode="transient", receipt_mode="not_found")
    job = claim_one(engine)
    assert job is not None
    run_delivery(engine, job, _handler(engine, provider))
    assert len(provider.calls) == 1

    # 重试前改绑：reconcile not_found → 允许重发，但重检必须 cancelled 而非投递。
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE gimbals SET bound_account_id = :acct, binding_revision = 2"
                 " WHERE id = :id"),
            {"acct": other, "id": gimbal},
        )
        conn.execute(
            text("UPDATE async_jobs SET status = 'queued', available_at = now(),"
                 " lease_owner = NULL, lease_revision = 0 WHERE id = ("
                 " SELECT id FROM async_jobs WHERE owner_id = :nid)"),
            {"nid": notification},
        )
    job2 = claim_one(engine, worker="notif-test-worker-r2")
    assert job2 is not None
    _, failure = run_delivery(engine, job2, _handler(engine, provider))

    assert failure is None
    row = fetch_notification(engine, notification)
    assert row["status"] == "cancelled"
    assert json.loads(row["last_error"])["reason"] == "binding_changed"
    assert len(provider.calls) == 1, "重检失败后不得再次调用推送"


def test_exhausted_transient_converges_t10_terminal_with_t12(
    engine: Engine,
) -> None:
    """Oracle #6 闭合：超过 max_attempts 时 T12 终态 failed，T10 同事务收敛终态。

    收敛计划随 DeliveryFailed 包装为 ``business_tx``，由 D 的 ``complete_failure``
    在同一事务执行——T10 不再滞留可观测 ``sending``。
    """
    _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=1)
    provider = DevTestDoublePushProvider(mode="transient")
    job = claim_one(engine)
    assert job is not None

    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None and failure.retryable is True
    assert failure.business_tx is not None, "末次失败必须携带 T10 收敛回调"
    assert fetch_job(engine, job_id)["status"] == "failed"
    row = fetch_notification(engine, notification)
    assert row["status"] == "failed", "超过 max_attempts 不得让 T10 停在 sending"
    terr = json.loads(row["last_error"])
    assert terr["code"] == "provider_transient"
    assert "retryable" in terr
    conv = getattr(failure, "convergence", None)
    assert conv is not None and conv.status == "failed"
    assert conv.last_error["code"] == "provider_transient"
    assert fetch_job(engine, job_id)["attempt_count"] == 1

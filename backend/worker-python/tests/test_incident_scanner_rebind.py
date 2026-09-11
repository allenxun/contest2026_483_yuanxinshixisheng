"""Python 必测 19（SC-R-03）：改绑后为 B 新建行、旧行收件人不改写，
旧行经 handler 重检 cancelled、新行可投递（真实 PG @55435）。"""
from __future__ import annotations

import uuid

from sqlalchemy import Engine, text
from test_notification_support import (
    claim_one,
    device_episode,
    enqueue_deliver_job,
    fetch_notification,
    run_delivery,
    seed_account,
    seed_destination,
    seed_gimbal,
)

from mvp_worker.notifications.config import NotificationSettings
from mvp_worker.notifications.push import DevTestDoublePushProvider
from mvp_worker.notifications.session_probe import DevDbSessionProbe
from mvp_worker.handlers.notification_deliver import NotificationDeliverHandler
from mvp_worker.scanners.incident_scanner import run_once


def test_rebind_creates_new_row_and_never_rewrites_old_recipient(engine: Engine) -> None:
    account_a = seed_account(engine)
    account_b = seed_account(engine)
    incident = str(uuid.uuid4())
    gimbal = seed_gimbal(
        engine, account_id=account_a, binding_revision=1, status="offline",
        episodes=device_episode(incident),
    )
    dest_a = seed_destination(engine, account_id=account_a, revision=1, session_ref="sess-a")

    report1 = run_once(engine, NotificationSettings(offline_threshold_seconds=60))
    assert report1.failures == 0

    with engine.connect() as conn:
        row_a = conn.execute(
            text("SELECT id FROM notifications WHERE gimbal_id = :id AND account_id = :acct"),
            {"id": gimbal, "acct": account_a},
        ).scalar_one()

    # 改绑 B + B 有 active 目标
    dest_b = seed_destination(engine, account_id=account_b, revision=1, session_ref="sess-b")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE gimbals SET bound_account_id = :acct, binding_revision = 2"
                 " WHERE id = :id"),
            {"acct": account_b, "id": gimbal},
        )

    report2 = run_once(engine, NotificationSettings(offline_threshold_seconds=60))
    assert report2.failures == 0

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, account_id, binding_revision, destination_id FROM notifications"
                 " WHERE gimbal_id = :id ORDER BY binding_revision"),
            {"id": gimbal},
        ).mappings().all()
    assert len(rows) == 2
    old_row, new_row = rows[0], rows[1]
    assert old_row["account_id"] == account_a, "旧行收件人绝不能被改写"
    assert old_row["binding_revision"] == 1
    assert old_row["destination_id"] == dest_a
    assert new_row["account_id"] == account_b
    assert new_row["binding_revision"] == 2
    assert new_row["destination_id"] == dest_b

    # 旧行投递前重检 → cancelled，且不调用推送
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM async_jobs WHERE owner_id = :id"), {"id": new_row["id"]}
        )
    provider = DevTestDoublePushProvider(mode="accepted")
    handler = NotificationDeliverHandler(
        push_provider=provider, session_probe=DevDbSessionProbe(engine)
    )
    old_job = claim_one(engine, worker="rebind-old")
    assert old_job is not None and old_job.owner_id == str(old_row["id"])
    _, failure = run_delivery(engine, old_job, handler)
    assert failure is None
    old_after = fetch_notification(engine, old_row["id"])
    assert old_after["status"] == "cancelled"
    assert provider.calls == []

    # 新行可投递（input_revision 语义 = destination_revision，非 binding_revision；
    # 新目标 dest_b 的 destination_revision=1，扫描器建行时即以此入队）。
    enqueue_deliver_job(engine, new_row["id"], input_revision=1)
    new_job = claim_one(engine, worker="rebind-new")
    assert new_job is not None and new_job.owner_id == str(new_row["id"])
    _, failure = run_delivery(engine, new_job, handler)
    assert failure is None
    assert fetch_notification(engine, new_row["id"])["status"] == "submitted"
    assert len(provider.calls) == 1

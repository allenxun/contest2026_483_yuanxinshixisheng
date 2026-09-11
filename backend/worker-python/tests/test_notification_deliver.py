"""Python 必测 11/12/15/16/20：投递成功链路、重检 cancelled、unknown 对账、
重复领取并发、通知内容合规（真实 PG @55435）。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import Engine, text
from test_notification_support import (
    PUSH_TEXT,
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


def _seed_linked(engine: Engine, *, session_ref: str = "sess-1"):
    account = seed_account(engine)
    incident = str(uuid.uuid4())
    gimbal = seed_gimbal(
        engine,
        account_id=account,
        binding_revision=1,
        status="online",
        episodes=device_episode(incident),
    )
    dest = seed_destination(engine, account_id=account, revision=1, session_ref=session_ref)
    notification = seed_notification(
        engine,
        gimbal_id=gimbal,
        incident_id=incident,
        account_id=account,
        binding_revision=1,
        destination_id=dest,
        destination_revision=1,
    )
    return account, incident, gimbal, dest, notification


def _handler(engine: Engine, provider: DevTestDoublePushProvider) -> NotificationDeliverHandler:
    return NotificationDeliverHandler(
        push_provider=provider, session_probe=DevDbSessionProbe(engine)
    )


# ---------------- 11. 投递成功链路 ----------------


def test_delivery_accepted_records_submitted(engine: Engine) -> None:
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None

    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is None
    row = fetch_notification(engine, notification)
    assert row["status"] == "submitted"
    assert row["provider_message_id"]
    assert fetch_job(engine, job_id)["status"] == "succeeded"
    assert len(provider.calls) == 1


def test_delivery_delivered_is_distinct_from_submitted(engine: Engine) -> None:
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="delivered")
    job = claim_one(engine)
    assert job is not None

    run_delivery(engine, job, _handler(engine, provider))

    row = fetch_notification(engine, notification)
    assert row["status"] == "delivered"
    assert row["provider_message_id"]
    assert fetch_job(engine, job_id)["status"] == "succeeded"


# ---------------- 12. 投递前重检 → cancelled，且不误发 ----------------


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("unbound", "binding_changed"),
        ("rebind", "binding_changed"),
        ("destination_revision", "destination_changed"),
        ("destination_status", "destination_changed"),
        ("incident_resolved", "incident_resolved"),
    ],
)
def test_precheck_cancels_without_sending(engine: Engine, mutation: str, reason: str) -> None:
    account, incident, gimbal, dest, notification = _seed_linked(engine)
    other = seed_account(engine)
    if mutation == "unbound":
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE gimbals SET bound_account_id = NULL WHERE id = :id"), {"id": gimbal})
    elif mutation == "rebind":
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE gimbals SET bound_account_id = :acct, binding_revision = 2"
                     " WHERE id = :id"),
                {"acct": other, "id": gimbal},
            )
    elif mutation == "destination_revision":
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE notification_destinations SET destination_revision = 2 WHERE id = :id"),
                {"id": dest},
            )
    elif mutation == "destination_status":
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE notification_destinations SET status = 'invalid' WHERE id = :id"),
                {"id": dest},
            )
    elif mutation == "incident_resolved":
        resolved = json.dumps({"schema_version": 1, "episodes": device_episode(
            incident, state="resolved")}, ensure_ascii=False)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE gimbals SET active_incidents = CAST(:j AS jsonb) WHERE id = :id"),
                {"j": resolved, "id": gimbal},
            )

    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is None
    row = fetch_notification(engine, notification)
    assert row["status"] == "cancelled"
    err = json.loads(row["last_error"])
    assert err["code"] == "route_recheck_failed"
    assert err["reason"] == reason
    assert err["retryable"] is False
    assert fetch_job(engine, job_id)["status"] == "succeeded"
    assert provider.calls == [], "重检失败绝不能调用推送"


def test_precheck_cancels_on_session_change_after_probe(engine: Engine) -> None:
    """恢复 C12 删除的 session_ref 子用例并强化为 TOCTOU 断言。

    锁外探针核验通过（返回旧会话快照）→ 在核验与加锁之间把 T09 session_ref
    改为另一值并按缺口 1 新语义递增 destination_revision → 加锁后必须发现
    会话变化、T10 cancelled、``last_error.reason='session_changed'``、推送零调用、
    ``provider_message_id`` 为空。
    """
    _, _, _, dest, notification = _seed_linked(engine, session_ref="sess-old")

    def mutate_session_between_probe_and_lock() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE notification_destinations"
                    " SET session_ref = 'sess-new',"
                    " destination_revision = destination_revision + 1"
                    " WHERE id = :id"
                ),
                {"id": dest},
            )

    class MutateAfterProbe(DevDbSessionProbe):
        """核验成功后、返回快照前改写 T09，模拟并发重登记 TOCTOU 窗口。"""

        def verify(self, *, account_id: str, destination_id: str,
                   destination_revision: int):
            snapshot = super().verify(
                account_id=account_id,
                destination_id=destination_id,
                destination_revision=destination_revision,
            )
            if snapshot is not None:
                mutate_session_between_probe_and_lock()
            return snapshot

    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None

    handler = NotificationDeliverHandler(
        push_provider=provider, session_probe=MutateAfterProbe(engine)
    )
    _, failure = run_delivery(engine, job, handler)

    assert failure is None
    row = fetch_notification(engine, notification)
    assert row["status"] == "cancelled"
    err = json.loads(row["last_error"])
    assert err["code"] == "route_recheck_failed"
    assert err["reason"] == "session_changed"
    assert err["retryable"] is False
    assert fetch_job(engine, job_id)["status"] == "succeeded"
    assert provider.calls == [], "会话变化绝不能调用推送"
    assert row["provider_message_id"] is None


# ---------------- 15. unknown 对账（B-14） ----------------


def test_unknown_does_not_resend_and_reconciles_accepted(engine: Engine) -> None:
    _, _, _, _, notification = _seed_linked(engine)
    enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="unknown")
    job = claim_one(engine)
    assert job is not None
    run_delivery(engine, job, _handler(engine, provider))

    row = fetch_notification(engine, notification)
    assert row["status"] == "unknown"
    assert len(provider.calls) == 1  # unknown 不重发

    # 模拟"发送后崩溃"：不调用完成写，直接把行置 sending + last_attempt_at。
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE notifications SET status = 'sending', attempt_count = 1,"
                 " last_attempt_at = now(), provider_message_id = NULL WHERE id = :id"),
            {"id": notification},
        )
        conn.execute(
            text("UPDATE async_jobs SET status = 'queued', available_at = now(),"
                 " lease_owner = NULL, lease_revision = 0, attempt_count = 0"
                 " WHERE owner_id = :id"),
            {"id": notification},
        )

    provider.set_receipt_mode("accepted")
    job2 = claim_one(engine, worker="notif-test-worker-2")
    assert job2 is not None
    _, failure = run_delivery(engine, job2, _handler(engine, provider))

    assert failure is None
    row = fetch_notification(engine, notification)
    assert row["status"] == "submitted"
    assert len(provider.calls) == 1, "对账成功不得产生第二次投递"
    assert provider.receipt_queries == [f"{notification}:1"]


def test_unknown_not_found_resends_same_provider_key(engine: Engine) -> None:
    _, _, _, _, notification = _seed_linked(engine)
    enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="accepted", receipt_mode="not_found")

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE notifications SET status = 'sending', attempt_count = 1,"
                 " last_attempt_at = now() WHERE id = :id"),
            {"id": notification},
        )
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is None
    assert len(provider.calls) == 1
    assert provider.calls[0].provider_message_key == f"{notification}:1"
    assert provider.receipt_queries == [f"{notification}:1"]
    assert fetch_notification(engine, notification)["status"] == "submitted"


# ---------------- 16. 重复领取/并发（SC-C-04） ----------------


def test_concurrent_claim_delivers_at_most_once(engine: Engine) -> None:
    _, _, _, _, notification = _seed_linked(engine)
    enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="accepted")

    results: list[bool] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        job = claim_one(engine, worker=name)
        if job is None:
            return
        run_delivery(engine, job, _handler(engine, provider))
        with lock:
            results.append(True)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(provider.calls) <= 1
    assert fetch_notification(engine, notification)["status"] == "submitted"


# ---------------- 20. 通知内容合规（B-15） ----------------


def test_payload_contains_no_identity_content(engine: Engine) -> None:
    account, incident, gimbal, _, notification = _seed_linked(engine)
    enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None
    run_delivery(engine, job, _handler(engine, provider))

    with engine.connect() as conn:
        payload_text = conn.execute(
            text("SELECT payload::text FROM notifications WHERE id = :id"), {"id": notification}
        ).scalar_one()
    payload = json.loads(payload_text)
    assert set(payload.keys()) == {
        "schema_version", "event_type", "incident_id", "gimbal_id", "text"
    }
    assert isinstance(payload["schema_version"], int) and not isinstance(payload["schema_version"], bool)
    assert payload["text"] == PUSH_TEXT
    for forbidden in (
        str(account),
        "member",
        "photo",
        "report",
        "phone",
        "+86",
        "face",
    ):
        assert forbidden not in payload_text
    assert provider.calls[0].text == PUSH_TEXT
    assert str(account) not in json.dumps(provider.calls[0].registration)

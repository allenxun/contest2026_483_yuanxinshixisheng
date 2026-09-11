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

from mvp_worker.notifications.push import DevTestDoublePushProvider, PushCall
from mvp_worker.notifications.session_probe import DevDbSessionProbe
from mvp_worker.notifications.config import NotificationSettings
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


# ---------------- BLOCKER D: T12 任务行业务绑定复核 ----------------
# 复现 Oracle BLOCKER D：合法 payload + 任意 owner_id / 陈旧 input_revision 等
# 仍可能投递并让 job 成功。现在必须在锁内重检中复核四项绑定，任一不符 → 绝不推送、
# T10 收敛 failed、T12 以 A 既有 UNSUPPORTED_CONTRACT 语义终结（retryable=false）。


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("owner_type", "owner_type_mismatch"),
        ("owner_id", "owner_id_mismatch"),
        ("input_revision", "input_revision_mismatch"),
        ("dedup_key", "dedup_key_mismatch"),
    ],
)
def test_contract_binding_mismatch_fails_without_sending(
    engine: Engine, mutation: str, reason: str
) -> None:
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    # 只改 T12 任务行的业务绑定（payload 仍合法），模拟"插入合法 payload 但配错 owner"。
    with engine.begin() as conn:
        if mutation == "owner_type":
            conn.execute(
                text("UPDATE async_jobs SET owner_type = 'app_account' WHERE id = :id"),
                {"id": job_id},
            )
        elif mutation == "owner_id":
            conn.execute(
                text("UPDATE async_jobs SET owner_id = :o WHERE id = :id"),
                {"o": uuid.uuid4(), "id": job_id},
            )
        elif mutation == "input_revision":
            conn.execute(
                text("UPDATE async_jobs SET input_revision = 2 WHERE id = :id"),
                {"id": job_id},
            )
        elif mutation == "dedup_key":
            conn.execute(
                text("UPDATE async_jobs SET dedup_key = 'wrong:key' WHERE id = :id"),
                {"id": job_id},
            )

    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None
    assert failure.code == "UNSUPPORTED_CONTRACT"
    assert failure.retryable is False
    job_row = fetch_job(engine, job_id)
    assert job_row["status"] == "failed"
    jerr = json.loads(job_row["last_error"])
    assert jerr["code"] == "UNSUPPORTED_CONTRACT"
    assert jerr["retryable"] is False

    row = fetch_notification(engine, notification)
    assert row["status"] == "failed", "契约绑定不符时 T10 绝不停留 sending"
    nerr = json.loads(row["last_error"])
    assert nerr["code"] == "UNSUPPORTED_CONTRACT"
    assert nerr["reason"] == reason
    assert nerr["retryable"] is False
    assert provider.calls == [], "契约绑定不符绝不能调用推送"


# ---------------- 15. unknown 对账（B-14） ----------------


def test_unknown_reconciles_accepted_via_real_state_machine(engine: Engine) -> None:
    """BLOCKER E-1/E-2：unknown 不得再被当作"终态且 job 成功"断掉对账链。

    不手工把 T10 改回 sending（删除旧的测试技巧），而是让 provider 真实返回 unknown
    → T12 由 A 的退避重排队、T10 保留可对账 unknown → 仅推进退避时间后再驱动真实处理
    路径 → 查回执收敛 submitted，且推送替身调用计数仍为 1（无第二次投递）。
    """
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="unknown")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    # provider 返回 unknown：本次为可重试失败，T10 保留可对账 unknown，T12 未 succeeded。
    assert failure is not None and failure.retryable is True
    assert failure.code == "delivery_unknown"
    assert len(provider.calls) == 1  # unknown 绝不重发
    row = fetch_notification(engine, notification)
    assert row["status"] == "unknown"
    assert fetch_job(engine, job_id)["status"] == "queued"

    # 真实状态机再驱动：只推进退避时间（模拟退避到期），不伪造 T10 状态。
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET available_at = now() WHERE id = :id"), {"id": job_id}
        )
    provider.set_receipt_mode("accepted")
    job2 = claim_one(engine, worker="notif-test-worker-2")
    assert job2 is not None
    _, failure2 = run_delivery(engine, job2, _handler(engine, provider))

    assert failure2 is None
    row = fetch_notification(engine, notification)
    assert row["status"] == "submitted"
    assert len(provider.calls) == 1, "对账成功不得产生第二次投递"
    assert provider.receipt_queries == [f"{notification}:1"]
    assert fetch_job(engine, job_id)["status"] == "succeeded"


def test_last_attempt_receipt_query_error_converges_t10(engine: Engine) -> None:
    """BLOCKER E-3：末次尝试回执查询抛异常 → T12 failed 且 T10 不再 sending/unknown。

    真实状态机：第一次 provider unknown（非末次）→ T10 unknown；第二次（末次）
    回执查询抛异常，必须在同一原子写里把 T10 收敛为明确终态并记 last_error。
    """
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=2)

    class RaisingReceiptProvider(DevTestDoublePushProvider):
        def query_receipt(self, provider_message_key: str):
            self.receipt_queries.append(provider_message_key)
            raise RuntimeError("receipt backend down")

    provider = RaisingReceiptProvider(mode="unknown")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))
    assert failure is not None and failure.retryable is True
    assert fetch_notification(engine, notification)["status"] == "unknown"

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET available_at = now() WHERE id = :id"), {"id": job_id}
        )
    job2 = claim_one(engine, worker="notif-test-worker-2")
    assert job2 is not None and job2.attempt_count == job2.max_attempts
    _, failure2 = run_delivery(engine, job2, _handler(engine, provider))

    assert failure2 is not None and failure2.code == "receipt_query_failed"
    assert failure2.retryable is True
    assert fetch_job(engine, job_id)["status"] == "failed"
    row = fetch_notification(engine, notification)
    assert row["status"] == "failed", "末次对账异常不得让 T10 停在 sending/unknown"
    err = json.loads(row["last_error"])
    assert err["code"] == "receipt_query_failed"
    assert err["retryable"] is False
    assert len(provider.calls) == 1
    assert provider.receipt_queries == [f"{notification}:1"]


def test_last_attempt_provider_exception_converges_t10(engine: Engine) -> None:
    """BLOCKER E-3：末次尝试 provider 抛异常 → T12 failed 且 T10 不滞留 sending。

    T10 先被锁内置 sending（提交后才发送），随后 provider 抛异常；末次尝试必须把
    T10 从 sending 收敛为 failed 并写 last_error。
    """
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=1)

    class RaisingDeliverProvider(DevTestDoublePushProvider):
        def deliver(self, *, registration, text, provider_message_key):
            self.calls.append(
                PushCall(provider_message_key=provider_message_key, text=text,
                         registration=registration)
            )
            raise RuntimeError("push backend down")

    provider = RaisingDeliverProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None and failure.code == "provider_transient"
    assert failure.retryable is True
    assert fetch_job(engine, job_id)["status"] == "failed"
    row = fetch_notification(engine, notification)
    assert row["status"] == "failed", "末次 provider 异常不得让 T10 停在 sending"
    err = json.loads(row["last_error"])
    assert err["code"] == "provider_transient"
    assert err["retryable"] is False
    assert len(provider.calls) == 1


def test_unknown_reconcile_boundary_exhausted_converges(engine: Engine) -> None:
    """BLOCKER E-1：对账必须有界——维持 unknown 策略下边界耗尽即收敛终态、不再增长。"""
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=2)
    provider = DevTestDoublePushProvider(mode="unknown", receipt_mode="not_found")
    handler = NotificationDeliverHandler(
        push_provider=provider,
        session_probe=DevDbSessionProbe(engine),
        settings=NotificationSettings(resend_on_not_found=False),
    )
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, handler)
    assert failure is not None and failure.retryable is True
    assert len(provider.calls) == 1

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET available_at = now() WHERE id = :id"), {"id": job_id}
        )
    job2 = claim_one(engine, worker="notif-test-worker-2")
    assert job2 is not None and job2.attempt_count == job2.max_attempts
    _, failure2 = run_delivery(engine, job2, handler)

    assert failure2 is not None and failure2.code == "delivery_unknown"
    assert fetch_job(engine, job_id)["status"] == "failed"
    row = fetch_notification(engine, notification)
    assert row["status"] == "failed"
    assert json.loads(row["last_error"])["code"] == "delivery_unknown"
    assert len(provider.calls) == 1, "维持 unknown 策略下不得重发"
    assert provider.receipt_queries == [f"{notification}:1"]
    # 终态后不再被领取，attempt_count 停止增长（无无限对账循环）。
    assert claim_one(engine, worker="notif-test-worker-3") is None
    assert fetch_job(engine, job_id)["attempt_count"] == 2


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

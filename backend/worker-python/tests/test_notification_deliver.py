"""Python 必测 11/12/15/16/20：投递成功链路、重检 cancelled、unknown 对账、
重复领取并发、通知内容合规（真实 PG @55435）。"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import Engine, text
from b_support import b_clean_tables  # noqa: F401  autouse B 自清（按 FK 顺序清 B 自己的行）
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
from mvp_worker.handlers.notification_deliver import (
    NotificationDeliverHandler,
    StaleNotification,
    converge_t10_tx,
)
from mvp_worker.runtime.complete import StaleGeneration


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


# ---------------- Oracle #5: T12 业务绑定复核覆盖所有路径 ----------------
# 校验在 handle() 进入任何状态分支之前执行；不符 → 绝不推送、绝不发布投递结果。
# 身份绑定不符 → UNSUPPORTED_CONTRACT（T12 failed）；input_revision 滞后 → 路由过期
# cancelled。失败路径不独立提交 T10（Oracle #6）：收敛计划随 DeliveryFailed 携带，
# 由 D 的 complete_failure callback 同事务执行（见 notification-adapter-handoff.md）。


def _mutate_job_binding(engine: Engine, job_id: uuid.UUID, mutation: str) -> None:
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
        elif mutation == "dedup_key":
            conn.execute(
                text("UPDATE async_jobs SET dedup_key = 'wrong:key' WHERE id = :id"),
                {"id": job_id},
            )


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("owner_type", "owner_type_mismatch"),
        ("owner_id", "owner_id_mismatch"),
        ("dedup_key", "dedup_key_mismatch"),
    ],
)
def test_unsupported_binding_mismatch_fails_without_publishing(
    engine: Engine, mutation: str, reason: str
) -> None:
    """Oracle #5：合法 payload + 错误身份绑定 → 绝不推送、绝不发布投递结果。"""
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    _mutate_job_binding(engine, job_id, mutation)
    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None
    assert failure.code == "UNSUPPORTED_CONTRACT"
    assert failure.retryable is False
    # T12 由 A 既有 complete_failure（lease 守卫）终结 failed。
    job_row = fetch_job(engine, job_id)
    assert job_row["status"] == "failed"
    jerr = json.loads(job_row["last_error"])
    assert jerr["code"] == "UNSUPPORTED_CONTRACT"
    assert jerr["retryable"] is False
    # Oracle #6：终态绑定不符经 D 的 complete_failure 同事务收敛 T10 → 不再滞留。
    row = fetch_notification(engine, notification)
    assert row["status"] == "failed", "终态失败必须同事务收敛 T10"
    terr = json.loads(row["last_error"])
    assert terr["code"] == "UNSUPPORTED_CONTRACT"
    assert terr["reason"] == reason
    assert terr["retryable"] is False
    assert provider.calls == [], "绑定不符绝不能调用推送"
    # 收敛计划包装为同事务 callback 随异常携带（供 D 的 complete_failure 执行）。
    assert failure.business_tx is not None, "终态失败必须携带 T10 收敛回调"
    conv = getattr(failure, "convergence", None)
    assert conv is not None
    assert conv.status == "failed"
    assert conv.last_error["code"] == "UNSUPPORTED_CONTRACT"
    assert conv.last_error["reason"] == reason


def test_input_revision_stale_cancels_route_expired(engine: Engine) -> None:
    """input_revision 滞后于 T10.destination_revision → 路由过期 cancelled，非误发。"""
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=2)  # != T10 的 1
    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is None
    row = fetch_notification(engine, notification)
    assert row["status"] == "cancelled"
    err = json.loads(row["last_error"])
    assert err["code"] == "route_recheck_failed"
    assert err["reason"] == "input_revision_stale"
    assert fetch_job(engine, job_id)["status"] == "succeeded"
    assert provider.calls == [], "路由过期绝不能调用推送"


def test_reconcile_branch_wrong_binding_never_publishes_submitted(engine: Engine) -> None:
    """Oracle #5 复现：T10 sending/unknown + 错误 T12 + 回执 accepted。

    修复前会经 `_reconcile_finalize_tx` 发布 submitted；现在必须在状态分支之前拦截，
    且不得调用回执查询/推送。
    """
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="unknown")
    # 真实状态机：provider unknown → T10 保持 sending、T12 退避重排队。
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))
    assert failure is not None and failure.retryable is True
    assert fetch_notification(engine, notification)["status"] == "sending"

    # 仅改 T12 绑定（owner_id）；回执将返回 accepted；推进退避后驱动真实路径。
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE async_jobs SET available_at = now(), owner_id = :o WHERE id = :id"),
            {"o": uuid.uuid4(), "id": job_id},
        )
    provider.set_receipt_mode("accepted")
    job2 = claim_one(engine, worker="notif-test-worker-2")
    assert job2 is not None
    _, failure2 = run_delivery(engine, job2, _handler(engine, provider))

    assert failure2 is not None and failure2.code == "UNSUPPORTED_CONTRACT"
    assert fetch_job(engine, job_id)["status"] == "failed"
    assert provider.receipt_queries == [], "绑定不符必须在对账之前拦截"
    assert len(provider.calls) == 1, "不得产生第二次投递"
    # 未发布 submitted；终态绑定不符经 D 的 callback 同事务收敛 T10 failed。
    wrong = fetch_notification(engine, notification)
    assert wrong["status"] == "failed"
    assert json.loads(wrong["last_error"])["code"] == "UNSUPPORTED_CONTRACT"


def test_finalize_tx_rechecks_binding_and_does_not_write(engine: Engine) -> None:
    """Oracle #5：最终写回事务内复校绑定；不符则不写并整体回滚。

    直接以写回事务 callback 验证（不伪造 reconcile 前提）：T10 保持自然的 pending。
    """
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    job = claim_one(engine)
    assert job is not None
    wrong_job = replace(job, owner_id=str(uuid.uuid4()))
    handler = _handler(engine, DevTestDoublePushProvider(mode="accepted"))

    with engine.begin() as conn:
        with pytest.raises(StaleNotification):
            handler._finalize_tx(
                wrong_job, str(notification), 1, "submitted", "pid-1", None
            )(conn)

    row = fetch_notification(engine, notification)
    assert row["status"] == "pending", "写回事务内复校不符必须不写、不发布"
    assert row["provider_message_id"] is None


def test_terminal_noop_branch_still_validates_binding(engine: Engine) -> None:
    """Oracle #5：终态 no-op 分支不得绕过绑定校验（不得静默 succeeded）。"""
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE notifications SET status = 'submitted',"
                 " provider_message_id = 'old' WHERE id = :id"),
            {"id": notification},
        )
        conn.execute(
            text("UPDATE async_jobs SET owner_id = :o WHERE id = :id"),
            {"o": uuid.uuid4(), "id": job_id},
        )
    provider = DevTestDoublePushProvider(mode="accepted")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None and failure.code == "UNSUPPORTED_CONTRACT"
    assert fetch_job(engine, job_id)["status"] == "failed"
    row = fetch_notification(engine, notification)
    assert row["status"] == "submitted", "不得覆盖既有终态，也不得发布新投递结果"
    assert provider.calls == [], "终态分支绑定不符绝不能调用推送"


# ---------------- Oracle #6: converge_t10_tx 事务语义（供 D 同事务回调） ----------------


def test_converge_t10_tx_writes_on_same_connection(engine: Engine) -> None:
    _, _, _, _, notification = _seed_linked(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE notifications SET status = 'sending', attempt_count = 1,"
                 " last_attempt_at = now() WHERE id = :id"),
            {"id": notification},
        )
    err = {"code": "delivery_unknown", "reason": "boom", "retryable": False}
    with engine.begin() as conn:
        updated = converge_t10_tx(conn, str(notification), 1, "failed", err)
    assert updated is True
    row = fetch_notification(engine, notification)
    assert row["status"] == "failed"
    assert json.loads(row["last_error"])["code"] == "delivery_unknown"


def test_converge_t10_tx_guard_mismatch_is_idempotent_noop(engine: Engine) -> None:
    """守卫不符（attempt_count / 状态）→ 幂等 no-op、不抛异常、不覆盖新事实。"""
    _, _, _, _, notification = _seed_linked(engine)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE notifications SET status = 'sending', attempt_count = 2,"
                 " last_attempt_at = now() WHERE id = :id"),
            {"id": notification},
        )
    err = {"code": "delivery_unknown", "reason": "boom", "retryable": False}
    with engine.begin() as conn:
        # 代次不符：本次 attempt=1 而 DB 为 2。
        assert converge_t10_tx(conn, str(notification), 1, "failed", err) is False
    row = fetch_notification(engine, notification)
    assert row["status"] == "sending"
    assert row["last_error"] is None

    # 状态不符（已终态）：仍是 no-op、不覆盖。
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE notifications SET status = 'submitted' WHERE id = :id"),
            {"id": notification},
        )
    with engine.begin() as conn:
        assert converge_t10_tx(conn, str(notification), 2, "failed", err) is False
    assert fetch_notification(engine, notification)["status"] == "submitted"


def test_valid_lease_commits_t10_and_t12_terminal_together(engine: Engine) -> None:
    """Oracle #6 有效 lease 提交：末次瞬时失败 → T10 终态与 T12 failed 同时落库。"""
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=1)
    provider = DevTestDoublePushProvider(mode="transient")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None and failure.business_tx is not None
    t12 = fetch_job(engine, job_id)
    t10 = fetch_notification(engine, notification)
    assert t12["status"] == "failed", "T12 由守卫写落 failed"
    assert t10["status"] == "failed", "T10 与 T12 同事务落终态"
    terr = json.loads(t10["last_error"])
    assert terr["code"] == "provider_transient"
    assert "retryable" in terr
    assert len(provider.calls) == 1


def test_stale_lease_rolls_back_t10_convergence(engine: Engine) -> None:
    """Oracle #6 过期 lease 整体回滚：守卫 0 行 → StaleGeneration → T10 写不提交。

    W1 持有 lease；用内存中失配的 ``lease_revision``（等价 W2 接管后的代次）走失败
    完成路径。``complete_failure`` 先执行 T10 收敛 business_tx，再以 T12 守卫更新；
    守卫 0 行抛 :class:`StaleGeneration`，同一事务整体回滚——T10 不得被收敛终态，
    T12 也不得被 W1 改写。
    """
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=1)
    provider = DevTestDoublePushProvider(mode="transient")
    job = claim_one(engine)
    assert job is not None

    stale = replace(job, lease_revision=job.lease_revision + 1)
    with pytest.raises(StaleGeneration):
        run_delivery(engine, stale, _handler(engine, provider))

    row = fetch_notification(engine, notification)
    assert row["status"] == "sending", "过期领取者不得提交 T10 终态（业务写整体回滚）"
    assert row["last_error"] is None
    # T12 未被 W1 改写：仍是 W1 持有的 running 行。
    assert fetch_job(engine, job_id)["status"] == "running"


def test_non_terminal_failure_keeps_t10_observable_without_callback(engine: Engine) -> None:
    """非末次可重试失败：T10 保持可观测、无收敛回调、T12 退避重排队。"""
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=5)
    provider = DevTestDoublePushProvider(mode="transient")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    assert failure is not None and failure.retryable is True
    assert failure.business_tx is None, "非末次不得携带终态收敛回调"
    assert fetch_job(engine, job_id)["status"] == "queued"
    row = fetch_notification(engine, notification)
    assert row["status"] == "sending", "非末次 T10 保持可观测等待下一次领取"
    assert row["last_error"] is None


def test_terminal_business_tx_repeat_is_idempotent_noop(engine: Engine) -> None:
    """同一收敛回调重复执行：no-op、不抛异常、不覆盖新事实（幂等）。"""
    _, _, _, _, notification = _seed_linked(engine)
    enqueue_deliver_job(engine, notification, input_revision=1, max_attempts=1)
    provider = DevTestDoublePushProvider(mode="transient")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))
    assert failure is not None and failure.business_tx is not None
    before = fetch_notification(engine, notification)
    assert before["status"] == "failed"

    # 重复执行回调（守卫已处终态）→ 幂等 no-op，不抛异常、不覆盖。
    with engine.begin() as conn:
        failure.business_tx(conn)
    after = fetch_notification(engine, notification)
    assert after["status"] == "failed"
    assert after["last_error"] == before["last_error"]


# ---------------- 15. unknown 对账（B-14） ----------------


def test_unknown_reconciles_accepted_via_real_state_machine(engine: Engine) -> None:
    """Oracle #6/E：unknown 不再被当作"终态且 job 成功"断掉对账链。

    不手工把 T10 改回 sending（删除旧的测试技巧），而是让 provider 真实返回 unknown
    → T12 由 A 的退避重排队、T10 保持可对账 sending → 仅推进退避时间后再驱动真实处理
    路径 → 查回执收敛 submitted，且推送替身调用计数仍为 1（无第二次投递）。
    """
    _, _, _, _, notification = _seed_linked(engine)
    job_id = enqueue_deliver_job(engine, notification, input_revision=1)
    provider = DevTestDoublePushProvider(mode="unknown")
    job = claim_one(engine)
    assert job is not None
    _, failure = run_delivery(engine, job, _handler(engine, provider))

    # provider 返回 unknown：本次为可重试失败，T10 保持可对账 sending，T12 未 succeeded。
    assert failure is not None and failure.retryable is True
    assert failure.code == "delivery_unknown"
    assert len(provider.calls) == 1  # unknown 绝不重发
    row = fetch_notification(engine, notification)
    assert row["status"] == "sending"
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


def test_last_attempt_receipt_query_error_converges_t10_terminal(engine: Engine) -> None:
    """Oracle #6 闭合：末次回执查询异常 → T12 failed 且 T10 同事务收敛终态。

    真实状态机：第一次 provider unknown（非末次）→ T10 保持可观测 ``sending``；第二次
    （末次）回执查询抛异常。终态失败把收敛计划包装成 ``business_tx``，由 D 的
    ``complete_failure`` 在同一事务执行 → T10 不再滞留 ``sending``。
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
    # 非末次：T10 保持可观测 sending、不提前终态化、无收敛回调。
    assert fetch_notification(engine, notification)["status"] == "sending"
    assert failure.business_tx is None

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
    assert row["status"] == "failed", "末次失败必须同事务收敛 T10 终态"
    terr = json.loads(row["last_error"])
    assert terr["code"] == "receipt_query_failed"
    assert terr["reason"] == "RuntimeError"
    assert "retryable" in terr
    assert failure2.business_tx is not None, "末次失败必须携带 T10 收敛回调"
    conv = getattr(failure2, "convergence", None)
    assert conv is not None and conv.status == "failed"
    assert conv.last_error["code"] == "receipt_query_failed"
    assert len(provider.calls) == 1
    assert provider.receipt_queries == [f"{notification}:1"]


def test_last_attempt_provider_exception_converges_t10_terminal(engine: Engine) -> None:
    """Oracle #6 闭合：末次 provider 异常 → T12 failed 且 T10 同事务收敛终态。

    T10 先被锁内置 ``sending``（提交后才发送），随后 provider 抛异常；终态失败携带
    ``business_tx`` 收敛回调，由 D 的 ``complete_failure`` 同事务执行。
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
    assert row["status"] == "failed", "末次失败必须同事务收敛 T10 终态"
    terr = json.loads(row["last_error"])
    assert terr["code"] == "provider_transient"
    assert terr["reason"] == "RuntimeError"
    assert "retryable" in terr
    assert failure.business_tx is not None, "末次失败必须携带 T10 收敛回调"
    conv = getattr(failure, "convergence", None)
    assert conv is not None and conv.status == "failed"
    assert conv.last_error["code"] == "provider_transient"
    assert len(provider.calls) == 1


def test_unknown_reconcile_boundary_exhausted_stops_growth(engine: Engine) -> None:
    """Oracle #6 闭合：对账有界——边界耗尽即 T12 终态化、T10 同事务收敛、不再增长。"""
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
    assert row["status"] == "failed", "对账边界耗尽的末次失败必须同事务收敛 T10"
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

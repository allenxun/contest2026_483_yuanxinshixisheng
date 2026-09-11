"""``notification.deliver``：通知投递 handler（DD 9.5；lane-m5 第二部分）。

投递安全不变式：
- **锁外**先核实会话（探针返回 T09 事实快照，``None``=否定），再在短事务内按锁
  顺序 ``T03 gimbals → T09 notification_destinations → T10 notifications`` 逐表
  ``SELECT ... FOR UPDATE`` 重检绑定/目标/会话/episode，并把锁外快照与锁内 T09
  事实逐项比对（封堵核验→加锁之间的 TOCTOU）；任一不匹配 → T10
  ``status='cancelled'`` + 有界 ``last_error.reason``，**不调用推送**。
- 提交 ``sending`` 后才发送（发送后崩溃留下可观测 sending）。
- ``submitted`` = 通道可信受理；``delivered`` = 可信送达回执；二者可区分。
- 崩溃后（``sending`` + ``last_attempt_at``）先查回执对账，绝不盲目重发；
  ``not_found`` 且策略允许时用**同一** ``provider_message_key`` 有限重发。
- 推送网络调用在锁外，绝不用长事务包住。
- ``input_revision`` 选择见模块常量 ``INPUT_REVISION_SEMANTICS``：以 T10
  ``destination_revision``（路由快照代次）为准——投递重试期间它稳定，且正是
  实际参与复合唯一键/路由的身份；``attempt_count`` 每次重试都变，无法表达
  "同一逻辑输入"。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from . import HandlerContext, HandlerResult, JobFailed, UnsupportedPayload
from ..notifications.config import NotificationSettings, load_settings
from ..notifications.payload_schema import (
    NotificationDeliverPayloadValidator,
    PayloadValidationError,
)
from ..notifications.push import (
    KIND_ACCEPTED,
    KIND_DELIVERED,
    KIND_REJECTED,
    KIND_TRANSIENT,
    KIND_UNKNOWN,
    PushProvider,
    build_push_provider,
)
from ..notifications.session_probe import (
    SessionSnapshot,
    SessionVerifier,
    build_session_probe,
)
from ..runtime.rows import JobRow

JOB_TYPE = "notification.deliver"

#: T12.input_revision 语义（协调决策 3 二选一）：destination_revision。
INPUT_REVISION_SEMANTICS = "destination_revision"

#: 最小正文（DD 9.5）：绝不含成员/照片/报告/手机号/账号信息。
PUSH_TEXT = "云台状态异常，请查看"

#: 已是终态，重复领取/重复投递一律 no-op（不重发）。unknown 也不盲目重发。
_TERMINAL_STATUSES = ("submitted", "delivered", "cancelled", "failed", "unknown")

#: 可被本次尝试推进到 sending 的状态集合。
_SENDABLE_STATUSES = ("pending", "queued", "unknown", "sending")

log = logging.getLogger("mvp_worker.notification.deliver")


class StaleNotification(RuntimeError):
    """完成写回的代次守卫失败：业务事务整体回滚（结果不发布）。"""


@dataclass(frozen=True)
class NotificationRow:
    id: str
    gimbal_id: str
    incident_id: str
    event_type: str
    account_id: str
    binding_revision: int
    destination_id: str
    destination_revision: int
    payload: dict[str, Any]
    status: str
    attempt_count: int
    last_attempt_at: Any
    provider_message_id: Optional[str]
    last_error: Optional[str]


_SELECT_NOTIFICATION = text(
    """
SELECT id, gimbal_id, incident_id, event_type, account_id, binding_revision,
       destination_id, destination_revision, payload::text AS payload, status,
       attempt_count, last_attempt_at, provider_message_id,
       last_error::text AS last_error
FROM notifications
WHERE id = :id
"""
)


def _row_of(m: Any) -> NotificationRow:
    return NotificationRow(
        id=str(m["id"]),
        gimbal_id=str(m["gimbal_id"]),
        incident_id=str(m["incident_id"]),
        event_type=m["event_type"],
        account_id=str(m["account_id"]),
        binding_revision=int(m["binding_revision"]),
        destination_id=str(m["destination_id"]),
        destination_revision=int(m["destination_revision"]),
        payload=json.loads(m["payload"]) if m["payload"] else {},
        status=m["status"],
        attempt_count=int(m["attempt_count"]),
        last_attempt_at=m["last_attempt_at"],
        provider_message_id=m["provider_message_id"],
        last_error=m["last_error"],
    )


class NotificationDeliverHandler:
    name = "notification-deliver"

    def __init__(
        self,
        *,
        push_provider: Optional[PushProvider] = None,
        session_probe: Optional[SessionVerifier] = None,
        settings: Optional[NotificationSettings] = None,
    ) -> None:
        self._push = push_provider
        self._probe = session_probe
        self._settings = settings
        self._validator = NotificationDeliverPayloadValidator()

    # ---------------- handler protocol ----------------

    def validate(self, payload: object) -> None:
        try:
            self._validator.validate(payload)
        except PayloadValidationError as exc:
            raise UnsupportedPayload(str(exc)) from exc

    def handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        notification_id = str(job.payload.get("notification_id"))
        settings = self._settings or load_settings()

        row = self._load(ctx.engine, notification_id)
        if row is None:
            raise JobFailed("notification_missing", "notification row not found", retryable=False)
        if row.status in _TERMINAL_STATUSES:
            # 终态幂等：已被正确取消/投递/失败的通知不重复投递（SC-C-04）。
            log.info(
                "notification.terminal_noop",
                extra={"notificationId": row.id, "status": row.status, "jobId": job.id},
            )
            return HandlerResult(business_tx=None)

        # 仅非终态才需要推送端口/会话探针（终态 no-op 不触碰供应商配置）。
        provider, probe = self._deps(ctx.engine, settings)

        if row.status == "sending" and row.last_attempt_at is not None:
            if settings.reconcile_unknown:
                return self._reconcile(ctx, job, row, provider, probe, settings)
            # 关闭对账策略时绝不盲目重发：标 unknown 收尾。
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, row.attempt_count, "unknown", None,
                    _error("delivery_unknown", "reconciliation disabled by policy", retryable=False),
                )
            )

        new_attempt = row.attempt_count + 1
        return self._precheck_and_send(
            ctx, job, row, provider, probe, new_attempt, f"{row.id}:{new_attempt}"
        )

    # ---------------- dependency wiring ----------------

    def _deps(
        self, engine: Engine, settings: NotificationSettings
    ) -> tuple[PushProvider, SessionVerifier]:
        try:
            provider = self._push or build_push_provider(settings)
            probe = self._probe or build_session_probe(engine, settings)
        except RuntimeError as exc:
            # 生产无真实实现 → fail-closed（绝不默认放行）；永久失败不重试循环。
            raise JobFailed("provider_not_configured", str(exc)[:200], retryable=False) from exc
        return provider, probe

    # ---------------- unknown reconciliation (B-14) ----------------

    def _reconcile(
        self,
        ctx: HandlerContext,
        job: JobRow,
        row: NotificationRow,
        provider: PushProvider,
        probe: SessionVerifier,
        settings: NotificationSettings,
    ) -> Optional[HandlerResult]:
        if ctx.abort_event.is_set():
            return None
        provider_key = f"{row.id}:{row.attempt_count}"
        try:
            receipt = provider.query_receipt(provider_key)
        except Exception as exc:  # 探针不可用 → 不臆断，退避重试
            raise JobFailed("receipt_query_failed", type(exc).__name__, retryable=True) from exc

        if receipt.kind == KIND_ACCEPTED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, row.attempt_count, "submitted", receipt.provider_message_id, None
                )
            )
        if receipt.kind == KIND_DELIVERED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, row.attempt_count, "delivered", receipt.provider_message_id, None
                )
            )
        if receipt.kind == "not_found":
            if settings.resend_on_not_found:
                # 同一 provider key → 通道侧幂等。
                return self._precheck_and_send(
                    ctx, job, row, provider, probe, row.attempt_count, provider_key
                )
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, row.attempt_count, "unknown", None,
                    _error("delivery_unknown", "receipt not found after crash", retryable=False),
                )
            )
        raise JobFailed("receipt_query_failed", f"unknown receipt kind {receipt.kind}",
                        retryable=True)

    # ---------------- pre-check + send ----------------

    def _precheck_and_send(
        self,
        ctx: HandlerContext,
        job: Optional[JobRow],
        row: NotificationRow,
        provider: PushProvider,
        probe: Optional[SessionVerifier],
        new_attempt: int,
        provider_key: str,
    ) -> Optional[HandlerResult]:
        # 3. 锁外核实会话（探针异常 → 不投递、可重试）。
        #    探针返回锁外读到的 T09 快照；None = 否定（不直接发送）。
        try:
            verified_snapshot: Optional[SessionSnapshot] = (
                probe.verify(
                    account_id=row.account_id,
                    destination_id=row.destination_id,
                    destination_revision=row.destination_revision,
                )
                if probe is not None
                else None
            )
        except Exception as exc:
            raise JobFailed("session_unverified", type(exc).__name__, retryable=True) from exc
        if verified_snapshot is None:
            # 探针否定：仍进入短事务重检，由重检判定并 cancelled（不直接发送）。
            log.info("notification.session_unverified", extra={"notificationId": row.id})
        if ctx.abort_event.is_set():
            return None

        # 5. 短事务重检 + 置 sending（提交后才发送）；把锁外快照带入锁内复核，
        #    封堵"核验之后、加锁之前"目标被改写的 TOCTOU 窗口。
        outcome = self._recheck_and_mark(ctx.engine, row, new_attempt, verified_snapshot)
        if outcome.cancelled:
            log.info(
                "notification.cancelled",
                extra={"notificationId": row.id, "reason": outcome.reason},
            )
            return HandlerResult(business_tx=None)
        if ctx.abort_event.is_set():
            return None

        # 6. 锁外发送
        try:
            result = provider.deliver(
                registration=outcome.registration or {},
                text=PUSH_TEXT,
                provider_message_key=provider_key,
            )
        except Exception as exc:
            raise JobFailed("provider_transient", type(exc).__name__, retryable=True) from exc
        if ctx.abort_event.is_set():
            return None

        if result.kind == KIND_ACCEPTED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, new_attempt, "submitted", result.provider_message_id, None
                )
            )
        if result.kind == KIND_DELIVERED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, new_attempt, "delivered", result.provider_message_id, None
                )
            )
        if result.kind == KIND_REJECTED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, new_attempt, "failed", None,
                    _error("provider_rejected", result.reason or "provider rejected",
                           retryable=False),
                )
            )
        if result.kind == KIND_UNKNOWN:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    row.id, new_attempt, "unknown", None,
                    _error("delivery_unknown", result.reason or "delivery unknown",
                           retryable=False),
                )
            )
        if result.kind == KIND_TRANSIENT:
            exhausted = job is not None and job.attempt_count >= job.max_attempts
            if exhausted:
                # T12 将落 failed；先把 T10 从 sending 收尾，避免永久卡在 sending。
                self._mark_terminal(
                    ctx.engine, row.id, new_attempt, "failed",
                    _error("provider_transient", result.reason or "provider transient",
                           retryable=False),
                )
            raise JobFailed("provider_transient", result.reason or "provider transient",
                            retryable=True)
        raise JobFailed("provider_transient", f"unknown outcome kind {result.kind}",
                        retryable=True)

    # ---------------- short transactional re-check ----------------

    @dataclass
    class _Recheck:
        cancelled: bool
        reason: Optional[str] = None
        registration: Optional[dict[str, Any]] = None

    def _recheck_and_mark(
        self,
        engine: Engine,
        row: NotificationRow,
        new_attempt: int,
        verified_snapshot: Optional[SessionSnapshot],
    ) -> "NotificationDeliverHandler._Recheck":
        with engine.begin() as conn:
            t03 = conn.execute(
                text(
                    "SELECT bound_account_id, binding_revision,"
                    " active_incidents::text AS active_incidents"
                    " FROM gimbals WHERE id = :gid FOR UPDATE"
                ),
                {"gid": row.gimbal_id},
            ).mappings().first()
            t09 = conn.execute(
                text(
                    "SELECT account_id, destination_revision, session_ref, status,"
                    " registration::text AS registration"
                    " FROM notification_destinations WHERE id = :did FOR UPDATE"
                ),
                {"did": row.destination_id},
            ).mappings().first()
            t10 = conn.execute(
                text(
                    "SELECT status, attempt_count FROM notifications"
                    " WHERE id = :nid FOR UPDATE"
                ),
                {"nid": row.id},
            ).mappings().first()
            if t10 is None:
                raise JobFailed("notification_missing", "notification disappeared", retryable=False)

            # 先比对锁外快照与锁内事实（TOCTOU），再比对 T10 快照代次。
            reason = self._snapshot_mismatch(verified_snapshot, t09)
            if reason is None:
                reason = self._mismatch(row, t03, t09)
            if reason is not None:
                conn.execute(
                    text(
                        "UPDATE notifications SET status = 'cancelled',"
                        " last_error = CAST(:err AS jsonb), updated_at = now()"
                        " WHERE id = :nid AND status IN"
                        " ('pending','queued','sending','unknown')"
                    ),
                    {"err": json.dumps(_error("route_recheck_failed", reason, retryable=False)),
                     "nid": row.id},
                )
                return NotificationDeliverHandler._Recheck(cancelled=True, reason=reason)

            res = conn.execute(
                text(
                    "UPDATE notifications SET status = 'sending',"
                    " attempt_count = :newatt, last_attempt_at = now(), updated_at = now()"
                    " WHERE id = :nid AND status IN ('pending','queued','sending','unknown')"
                    " AND attempt_count = :oldatt"
                ),
                {"newatt": new_attempt, "nid": row.id, "oldatt": row.attempt_count},
            )
            if res.rowcount == 0:
                raise JobFailed("delivery_contended", "concurrent delivery attempt",
                                retryable=True)
            registration = json.loads(t09["registration"]) if t09 and t09["registration"] else {}
        return NotificationDeliverHandler._Recheck(cancelled=False, registration=registration)

    @staticmethod
    def _snapshot_mismatch(
        snapshot: Optional[SessionSnapshot], t09: Any
    ) -> Optional[str]:
        """把锁外核验快照与锁内 T09 事实逐项比对（TOCTOU 检测）。

        - ``session_ref`` 变化 → ``session_changed``（优先于代次，因为同内容
          重登记换会话已按新语义递增代次，语义上应先报会话变化）。
        - ``account_id``/``destination_revision``/``status`` 变化 → ``destination_changed``。
        - 探针否定（``snapshot is None``）时不臆断，交回 T10 快照重检判定。
        """
        if snapshot is None:
            return None
        if t09 is None:
            return "destination_changed"
        if t09["session_ref"] != snapshot.session_ref:
            return "session_changed"
        if str(t09["account_id"]) != snapshot.account_id:
            return "destination_changed"
        if int(t09["destination_revision"]) != snapshot.destination_revision:
            return "destination_changed"
        if t09["status"] != snapshot.status:
            return "destination_changed"
        return None

    @staticmethod
    def _mismatch(row: NotificationRow, t03: Any, t09: Any) -> Optional[str]:
        if t03 is None:
            return "binding_changed"
        if t03["bound_account_id"] is None or str(t03["bound_account_id"]) != row.account_id:
            return "binding_changed"
        if int(t03["binding_revision"]) != row.binding_revision:
            return "binding_changed"
        if t09 is None:
            return "destination_changed"
        if str(t09["account_id"]) != row.account_id:
            return "destination_changed"
        if int(t09["destination_revision"]) != row.destination_revision:
            return "destination_changed"
        if t09["status"] != "active":
            return "destination_changed"
        if not _episode_active(t03["active_incidents"], row.incident_id):
            return "incident_resolved"
        return None

    # ---------------- final business writes ----------------

    def _finalize_tx(
        self,
        notification_id: str,
        attempt: int,
        status: str,
        provider_message_id: Optional[str],
        last_error: Optional[dict[str, Any]],
    ):
        def tx(conn: Connection) -> None:
            res = conn.execute(
                text(
                    "UPDATE notifications SET status = :st, provider_message_id = :mid,"
                    " last_error = CAST(:err AS jsonb), updated_at = now()"
                    " WHERE id = :nid AND status = 'sending' AND attempt_count = :att"
                ),
                {
                    "st": status,
                    "mid": provider_message_id,
                    "err": None if last_error is None else json.dumps(last_error),
                    "nid": notification_id,
                    "att": attempt,
                },
            )
            if res.rowcount == 0:
                # 代次失效：整体回滚，结果不发布。
                raise StaleNotification(
                    f"notification {notification_id} stale generation on finalize"
                )

        return tx

    def _mark_terminal(
        self,
        engine: Engine,
        notification_id: str,
        attempt: int,
        status: str,
        last_error: dict[str, Any],
    ) -> None:
        with engine.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE notifications SET status = :st,"
                    " last_error = CAST(:err AS jsonb), updated_at = now()"
                    " WHERE id = :nid AND status = 'sending' AND attempt_count = :att"
                ),
                {"st": status, "err": json.dumps(last_error), "nid": notification_id,
                 "att": attempt},
            )
            if res.rowcount == 0:
                raise StaleNotification(
                    f"notification {notification_id} stale generation on terminal mark"
                )

    # ---------------- load ----------------

    @staticmethod
    def _load(engine: Engine, notification_id: str) -> Optional[NotificationRow]:
        with engine.connect() as conn:
            m = conn.execute(_SELECT_NOTIFICATION, {"id": notification_id}).mappings().first()
        return None if m is None else _row_of(m)


def _episode_active(active_incidents_text: Optional[str], incident_id: str) -> bool:
    if not active_incidents_text:
        return False
    try:
        data = json.loads(active_incidents_text)
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    episodes = data.get("episodes")
    if not isinstance(episodes, dict):
        return False
    episode = episodes.get(incident_id)
    return isinstance(episode, dict) and episode.get("state") == "active"


def _error(code: str, reason: str, *, retryable: bool) -> dict[str, Any]:
    """有界诊断 last_error（自由格式，不受 schema_version 约束）。"""
    return {"code": code, "reason": reason, "retryable": retryable}


handler = NotificationDeliverHandler()

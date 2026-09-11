"""``notification.deliver``：通知投递 handler（DD 9.5；lane-m5 第二部分）。

投递安全不变式：
- **锁外**先核实会话（探针返回 T09 事实快照，``None``=否定），再在短事务内按锁
  顺序 ``T03 gimbals → T09 notification_destinations → T10 notifications`` 逐表
  ``SELECT ... FOR UPDATE`` 重检绑定/目标/会话/episode，并把锁外快照与锁内 T09
  事实逐项比对（封堵核验→加锁之间的 TOCTOU）；任一不匹配 → T10
  ``status='cancelled'`` + 有界 ``last_error.reason``，**不调用推送**。
- 提交 ``sending`` 后才发送（发送后崩溃留下可观测 sending）。
- ``submitted`` = 通道可信受理；``delivered`` = 可信送达回执；二者可区分。
- 崩溃后（``sending`` + ``last_attempt_at``）或通道结果不确定（``unknown``）都先查
  回执对账，绝不盲目重发；``not_found`` 且策略允许时用**同一**
  ``provider_message_key`` 有限重发。``unknown`` 不再是"终态且 job 成功"：
  它保留为**可继续对账**的状态，由 A 的退避/``max_attempts`` 驱动下一次真实对账，
  边界耗尽后收敛为明确终态（``failed`` + ``last_error``）。
- 发送前的锁内重检额外复核 T12 任务行与 T10 的业务绑定
  （``owner_type``/``owner_id``/``input_revision``/``dedup_key``）；不符 → 绝不投递，
  T10 直接收敛 ``failed``，T12 以 A 既有 ``UNSUPPORTED_CONTRACT`` 语义终结（不重试）。
- 任何会让 T12 终结为 ``failed`` 的末次尝试路径（回执查询异常、provider 异常、
  重试耗尽），都在同一原子写里把 T10 从 ``sending``/``unknown`` 收敛为终态并记
  ``last_error``，绝不允许 T10 滞留 ``sending``。
- 推送网络调用在锁外，绝不用长事务包住。
- ``input_revision`` 选择见模块常量 ``INPUT_REVISION_SEMANTICS``：以 T10
  ``destination_revision``（路由快照代次）为准——投递重试期间它稳定，且正是
  实际参与复合唯一键/路由的身份；``attempt_count`` 每次重试都变，无法表达
  "同一逻辑输入"。
"""
from __future__ import annotations

import json
import logging
import uuid
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

#: 已是终态，重复领取/重复投递一律 no-op（不重发）。
#: 注意：unknown **不在**此列——它必须可继续对账（先查回执），绝不假成功。
_TERMINAL_STATUSES = ("submitted", "delivered", "cancelled", "failed")

#: 需要先查回执对账（而非直接投递）的状态集合：sending=发送后崩溃残留；
#: unknown=通道结果不确定。两者都携带 last_attempt_at 与稳定 provider key。
_RECONCILABLE_STATUSES = ("sending", "unknown")

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

        # sending=发送后崩溃残留；unknown=通道结果不确定。两者都必须先查回执对账，
        # 绝不再盲目重发（unknown 不再被当作"终态且 job 成功"）。
        if row.status in _RECONCILABLE_STATUSES and row.last_attempt_at is not None:
            if settings.reconcile_unknown:
                return self._reconcile(ctx, job, row, provider, probe, settings)
            # 关闭对账策略：不盲目重发，把崩溃残留/未知收敛为明确终态，绝不假成功。
            self._converge_t10(
                ctx.engine, row.id, row.attempt_count, "failed",
                _error("delivery_unknown", "reconciliation disabled by policy",
                       retryable=False),
            )
            raise JobFailed("delivery_unknown", "reconciliation disabled by policy",
                            retryable=False)

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
        # provider key 在 crash residue/unknown 期间保持稳定：notification id + 首次发送尝试号。
        provider_key = f"{row.id}:{row.attempt_count}"
        last_attempt = self._is_last_attempt(job)
        try:
            receipt = provider.query_receipt(provider_key)
        except Exception as exc:  # 回执通道不可用 → 不臆断
            self._converge_t10(
                ctx.engine, row.id, row.attempt_count,
                "failed" if last_attempt else "unknown",
                _error("receipt_query_failed", type(exc).__name__,
                       retryable=not last_attempt),
            )
            raise JobFailed("receipt_query_failed", type(exc).__name__, retryable=True) from exc

        if ctx.abort_event.is_set():
            return None
        if receipt.kind == KIND_ACCEPTED:
            return HandlerResult(
                business_tx=self._reconcile_finalize_tx(
                    row.id, row.attempt_count, "submitted", receipt.provider_message_id, None
                )
            )
        if receipt.kind == KIND_DELIVERED:
            return HandlerResult(
                business_tx=self._reconcile_finalize_tx(
                    row.id, row.attempt_count, "delivered", receipt.provider_message_id, None
                )
            )
        if receipt.kind == "not_found":
            if settings.resend_on_not_found:
                # 同一 provider key → 通道侧幂等；重发次数由 job max_attempts 兜底（有界）。
                return self._precheck_and_send(
                    ctx, job, row, provider, probe, row.attempt_count, provider_key
                )
            self._converge_t10(
                ctx.engine, row.id, row.attempt_count,
                "failed" if last_attempt else "unknown",
                _error("delivery_unknown", "receipt not found after crash",
                       retryable=not last_attempt),
            )
            raise JobFailed("delivery_unknown", "receipt not found after crash",
                            retryable=True)
        self._converge_t10(
            ctx.engine, row.id, row.attempt_count,
            "failed" if last_attempt else "unknown",
            _error("receipt_query_failed", f"unknown receipt kind {receipt.kind}",
                   retryable=not last_attempt),
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
        last_attempt = self._is_last_attempt(job)
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
            if last_attempt:
                # 末次尝试：T12 将终结 failed，必须同时把 T10（若在 sending/unknown）收敛。
                self._converge_t10(
                    ctx.engine, row.id, new_attempt, "failed",
                    _error("session_unverified", type(exc).__name__, retryable=False),
                )
            raise JobFailed("session_unverified", type(exc).__name__, retryable=True) from exc
        if verified_snapshot is None:
            # 探针否定：仍进入短事务重检，由重检判定并 cancelled（不直接发送）。
            log.info("notification.session_unverified", extra={"notificationId": row.id})
        if ctx.abort_event.is_set():
            return None

        # 5. 短事务重检 + 置 sending（提交后才发送）；把锁外快照带入锁内复核，
        #    封堵"核验之后、加锁之前"目标被改写的 TOCTOU 窗口。
        try:
            outcome = self._recheck_and_mark(
                ctx.engine, job, row, new_attempt, verified_snapshot
            )
        except JobFailed as exc:
            if last_attempt:
                # 重检异常（如并发争用）也不得让 T10 在末次尝试滞留 sending/unknown。
                self._converge_t10(
                    ctx.engine, row.id, new_attempt, "failed",
                    _error(exc.code, exc.message, retryable=False),
                )
            raise
        if outcome.unsupported_contract is not None:
            # T12 与 T10 的业务绑定不合法/陈旧（锁内已置 T10 failed）→ 绝不投递；
            # 按 A 既有 UNSUPPORTED_CONTRACT 语义终结 T12（failed / retryable=false）。
            raise JobFailed("UNSUPPORTED_CONTRACT", outcome.unsupported_contract,
                            retryable=False)
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
            # provider 异常不臆断通道事实：末次尝试必须原子收敛 T10（不留 sending）。
            if last_attempt:
                self._converge_t10(
                    ctx.engine, row.id, new_attempt, "failed",
                    _error("provider_transient", type(exc).__name__, retryable=False),
                )
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
            # 通道结果不确定：绝不把 T10 置"终态且 T12 成功"、断掉对账链。保留可对账
            # 状态 unknown，由 A 的退避驱动下一次真实回执查询；末次则收敛 failed。
            self._converge_t10(
                ctx.engine, row.id, new_attempt,
                "failed" if last_attempt else "unknown",
                _error("delivery_unknown", result.reason or "delivery unknown",
                       retryable=not last_attempt),
            )
            raise JobFailed("delivery_unknown", result.reason or "delivery unknown",
                            retryable=True)
        if result.kind == KIND_TRANSIENT:
            if last_attempt:
                # T12 将落 failed；先把 T10 从 sending 收尾，避免永久卡在 sending。
                self._converge_t10(
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
        #: 非 None = T12 任务行与 T10 业务绑定不符，T10 已在锁内收敛 failed。
        unsupported_contract: Optional[str] = None

    def _recheck_and_mark(
        self,
        engine: Engine,
        job: Optional[JobRow],
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
                    "SELECT status, attempt_count, destination_revision FROM notifications"
                    " WHERE id = :nid FOR UPDATE"
                ),
                {"nid": row.id},
            ).mappings().first()
            if t10 is None:
                raise JobFailed("notification_missing", "notification disappeared", retryable=False)

            # T12 任务行业务绑定复核（BLOCKER D）：必须精确指向本通知，且业务输入代次
            # 等于锁内当前 destination_revision（路由快照即业务输入）。不符 → 绝不投递。
            contract_reason = self._contract_mismatch(job, row, t10)
            if contract_reason is not None:
                conn.execute(
                    text(
                        "UPDATE notifications SET status = 'failed',"
                        " last_error = CAST(:err AS jsonb), updated_at = now()"
                        " WHERE id = :nid AND status IN"
                        " ('pending','queued','sending','unknown')"
                    ),
                    {"err": json.dumps(_error("UNSUPPORTED_CONTRACT", contract_reason,
                                              retryable=False)),
                     "nid": row.id},
                )
                return NotificationDeliverHandler._Recheck(
                    cancelled=False, unsupported_contract=contract_reason
                )

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

    @staticmethod
    def _contract_mismatch(
        job: Optional[JobRow], row: NotificationRow, t10: Any
    ) -> Optional[str]:
        """复核 T12 任务行与 T10 的业务绑定（BLOCKER D）。

        字段来源：``owner_type``/``owner_id``/``input_revision``/``dedup_key`` 全部来自
        ``claim_batch`` 的 :class:`JobRow` 行投影（A 的 ``_SELECT_CLAIMABLE`` 显式列出）；
        ``destination_revision`` 来自本事务内对 ``notifications`` 的单表 ``FOR UPDATE``
        读取（``t10``）。返回不匹配原因；全部匹配返回 ``None``。
        """
        if job is None:
            return "missing_job_binding"
        if job.job_type != JOB_TYPE:
            return "job_type_mismatch"
        if job.owner_type != "notification":
            return "owner_type_mismatch"
        try:
            same_owner = uuid.UUID(str(job.owner_id)) == uuid.UUID(str(row.id))
        except (ValueError, AttributeError, TypeError):
            same_owner = False
        if not same_owner:
            return "owner_id_mismatch"
        # input_revision 语义 = T10.destination_revision（路由快照即业务输入）。
        if int(job.input_revision) != int(t10["destination_revision"]):
            return "input_revision_mismatch"
        if job.dedup_key != f"notification:{row.id}":
            return "dedup_key_mismatch"
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

    def _reconcile_finalize_tx(
        self,
        notification_id: str,
        attempt: int,
        status: str,
        provider_message_id: Optional[str],
        last_error: Optional[dict[str, Any]],
    ):
        """对账收敛写回：T10 可能停在 ``sending``（崩溃）或 ``unknown``（结果不确定）。"""

        def tx(conn: Connection) -> None:
            res = conn.execute(
                text(
                    "UPDATE notifications SET status = :st, provider_message_id = :mid,"
                    " last_error = CAST(:err AS jsonb), updated_at = now()"
                    " WHERE id = :nid AND status IN ('sending','unknown')"
                    " AND attempt_count = :att"
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
                raise StaleNotification(
                    f"notification {notification_id} stale generation on reconcile"
                )

        return tx

    @staticmethod
    def _is_last_attempt(job: Optional[JobRow]) -> bool:
        """本次领取是否为最后一次尝试（``complete_failure`` 的失败判据一致）。"""
        return job is not None and job.attempt_count >= job.max_attempts

    def _converge_t10(
        self,
        engine: Engine,
        notification_id: str,
        attempt: int,
        status: str,
        last_error: dict[str, Any],
    ) -> bool:
        """把 ``sending``/``unknown`` 的 T10 原子收敛为明确终态。

        守卫谓词 ``id=? AND status IN ('sending','unknown') AND attempt_count=本次``
        与既有代次守卫一致：旧尝试绝不覆盖新事实；已是他态则幂等无操作（不抛异常，
        以便在失败路径上先收敛、再让运行时终结 T12）。
        """
        with engine.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE notifications SET status = :st,"
                    " last_error = CAST(:err AS jsonb), updated_at = now()"
                    " WHERE id = :nid AND status IN ('sending','unknown')"
                    " AND attempt_count = :att"
                ),
                {"st": status, "err": json.dumps(last_error), "nid": notification_id,
                 "att": attempt},
            )
            return res.rowcount > 0

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

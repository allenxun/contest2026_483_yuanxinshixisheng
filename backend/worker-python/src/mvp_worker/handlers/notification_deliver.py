"""``notification.deliver``：通知投递 handler（DD 9.5；lane-m5 第二部分）。

投递安全不变式：
- **锁外**先核实会话（探针返回 T09 事实快照，``None``=否定），再在短事务内按锁
  顺序 ``T03 gimbals → T09 notification_destinations → T10 notifications`` 逐表
  ``SELECT ... FOR UPDATE`` 重检绑定/目标/会话/episode，并把锁外快照与锁内 T09
  事实逐项比对（封堵核验→加锁之间的 TOCTOU）；任一不匹配 → T10
  ``status='cancelled'`` + 有界 ``last_error.reason``，**不调用推送**。
- 提交 ``sending`` 后才发送（发送后崩溃留下可观测 sending）。
- ``submitted`` = **提供方明确接受**（不代表设备已送达）；``delivered`` = 可信送达
  回执；二者可区分。
- 崩溃后（``sending`` + ``last_attempt_at``）或通道结果不确定（``unknown``）都先查
  回执对账，绝不盲目重发；``not_found`` 且策略允许时用**同一**
  ``provider_message_key`` 有限重发。``unknown`` 保留为**可继续对账**的状态，由 A 的
  退避/``max_attempts`` 驱动下一次真实对账。
- **T12 业务绑定复核（Oracle #5）**：``owner_type``/``owner_id``/``input_revision``/
  ``dedup_key`` 四项在 ``handle()`` **进入任何状态分支之前**校验一次，并在**最终写回
  事务内**（``_finalize_tx``/``_reconcile_finalize_tx``）复核一次；不符绝不投递、绝不
  发布 ``submitted``/``delivered``。
  - 身份绑定不符（``owner_type``/``owner_id``/``dedup_key``）→ ``UNSUPPORTED_CONTRACT``
    （``retryable=false``）终结 T12；
  - ``input_revision != T10.destination_revision``（路由快照代次推进）→ 路由过期，按
    发送前重检既有语义 ``cancelled`` + ``route_recheck_failed``，不误发。
- **失败路径 T10 与 T12 同事务收敛（Oracle #6）**：失败/收敛路径只 ``raise
  DeliveryFailed``；对**终态失败**（``retryable=false`` 或已达 ``max_attempts``），它把
  携带的 :class:`T10Convergence` 计划包装成 ``business_tx`` 闭包交给 D 的
  ``complete_failure``：同一事务内**先**执行 :func:`converge_t10_tx` 收敛 T10、**后**做
  T12 代次+租约守卫更新；守卫 0 行（过期领取者）→ ``StaleGeneration`` → 业务写与任务
  状态**整体回滚**。**非末次**可重试失败不包装回调，T10 保持 ``sending``/``unknown``
  可观测态等待下一次领取对账/重检（迟滞终态化由 D 的退避/``max_attempts`` 驱动）。
- 推送网络调用在锁外，绝不用长事务包住；退避重试有界（``max_attempts`` 硬边界），
  异常一律有 ``last_error.code/message/retryable`` 记录。
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
from typing import Any, Callable, Optional

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

#: T12 业务绑定复核分类（Oracle #5）。
_BINDING_UNSUPPORTED = "unsupported_contract"   # 身份绑定不符 → UNSUPPORTED_CONTRACT
_BINDING_ROUTE_EXPIRED = "route_expired"        # 路由快照代次推进 → cancelled

log = logging.getLogger("mvp_worker.notification.deliver")


@dataclass(frozen=True)
class T10Convergence:
    """失败路径期望的 T10 收敛计划（**B 不独立提交**，见 Oracle #6）。

    ``status == 'failed'`` 表示终态收敛，由 :class:`DeliveryFailed` 包装成
    ``business_tx`` 交给 D 的 ``complete_failure`` 同事务执行；``status == 'unknown'``
    表示非末次可重试失败，不包装回调、T10 保持可观测态。
    """

    notification_id: str
    attempt: int
    status: str
    last_error: dict[str, Any]


class DeliveryFailed(JobFailed):
    """携带 T10 收敛计划的 :class:`JobFailed`（B 不独立提交 T10）。

    ``convergence`` 为 ``None`` 表示该失败无需收敛 T10（例如 T10 行不存在）。
    普通 ``JobFailed`` 调用方仍按 A 既有 ``complete_failure`` 处理。

    **终态判据**：仅当 ``convergence.status == 'failed'``（即调用方已判定本次为永久
    失败或已达 ``max_attempts``）时，本类才把计划包装成 ``business_tx`` 闭包，随
    :class:`JobFailed` 交给 D 的 ``complete_failure`` 同事务执行。``status == 'unknown'``
    （非末次可重试）**不**包装回调：T10 保持可观测态，由下一次领取对账/重检。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        convergence: Optional[T10Convergence] = None,
    ) -> None:
        self.convergence = convergence
        # 终态失败 → 同事务 T10 收敛（D 的 complete_failure 先执行业务写再做 T12 守卫；
        # 守卫 0 行整体回滚）。非终态不包装，避免提前终态化。
        business_tx = (
            _converge_plan_tx(convergence)
            if convergence is not None and convergence.status == "failed"
            else None
        )
        super().__init__(code, message, retryable=retryable, business_tx=business_tx)



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

        # Oracle #5：T12 业务绑定必须在**进入任何状态分支之前**校验（终态 no-op /
        # sending/unknown 对账 / 直接发送都不得绕过），否则错误 T12 仍可能发布 submitted。
        binding = self._classify_binding(job, row.id, row.destination_revision)
        if binding is not None:
            kind, reason = binding
            if kind == _BINDING_UNSUPPORTED:
                # 绝不推送、绝不发布任何投递结果。终态 T10 收敛计划随 DeliveryFailed
                # 包装为 business_tx，由 D 的 complete_failure 同事务执行（B 不独立提交）。
                raise self._delivery_failed(
                    row.id, row.attempt_count, "failed",
                    "UNSUPPORTED_CONTRACT", reason, retryable=False,
                )
            # 路由快照代次已推进（换号/会话变化）→ 按发送前重检既有语义 cancelled。
            self._cancel_t10(ctx.engine, row.id, row.attempt_count, reason)
            return HandlerResult(business_tx=None)

        if row.status in _TERMINAL_STATUSES:
            # 终态幂等：已被正确取消/投递/失败的通知不重复投递（SC-C-04）。
            log.info(
                "notification.terminal_noop",
                extra={"notificationId": row.id, "status": row.status, "jobId": job.id},
            )
            return HandlerResult(business_tx=None)

        # 仅非终态才需要推送端口/会话探针（终态 no-op 不触碰供应商配置）。
        provider, probe = self._deps(ctx.engine, settings, row)

        # sending=发送后崩溃残留；unknown=通道结果不确定。两者都必须先查回执对账，
        # 绝不再盲目重发（unknown 不再被当作"终态且 job 成功"）。
        if row.status in _RECONCILABLE_STATUSES and row.last_attempt_at is not None:
            if settings.reconcile_unknown:
                return self._reconcile(ctx, job, row, provider, probe, settings)
            # 关闭对账策略：不盲目重发；T10 收敛计划交给 D 的同事务 callback。
            raise self._delivery_failed(
                row.id, row.attempt_count, "failed",
                "delivery_unknown", "reconciliation disabled by policy", retryable=False,
            )

        new_attempt = row.attempt_count + 1
        return self._precheck_and_send(
            ctx, job, row, provider, probe, new_attempt, f"{row.id}:{new_attempt}"
        )

    # ---------------- dependency wiring ----------------

    def _deps(
        self, engine: Engine, settings: NotificationSettings, row: NotificationRow
    ) -> tuple[PushProvider, SessionVerifier]:
        try:
            provider = self._push or build_push_provider(settings)
            probe = self._probe or build_session_probe(engine, settings)
        except RuntimeError as exc:
            # 生产无真实实现 → fail-closed（绝不默认放行）；永久失败不重试循环。
            # T12 依 `retryable=false` 终态化；T10 若仍未尝试（pending）也随同事务收敛，
            # 避免无后续领取时滞留。收敛计划随 DeliveryFailed 交给 D 的 callback。
            raise self._delivery_failed(
                row.id, row.attempt_count, "failed",
                "provider_not_configured", str(exc)[:200], retryable=False,
            ) from exc
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
            # 失败路径不独立提交 T10；收敛计划交给 D 的同事务 callback（见 handoff）。
            raise self._delivery_failed(
                row.id, row.attempt_count, "failed" if last_attempt else "unknown",
                "receipt_query_failed", type(exc).__name__, retryable=True,
            ) from exc

        if ctx.abort_event.is_set():
            return None
        if receipt.kind == KIND_ACCEPTED:
            return HandlerResult(
                business_tx=self._reconcile_finalize_tx(
                    job, row.id, row.attempt_count, "submitted",
                    receipt.provider_message_id, None,
                )
            )
        if receipt.kind == KIND_DELIVERED:
            return HandlerResult(
                business_tx=self._reconcile_finalize_tx(
                    job, row.id, row.attempt_count, "delivered",
                    receipt.provider_message_id, None,
                )
            )
        if receipt.kind == "not_found":
            if settings.resend_on_not_found:
                # 同一 provider key → 通道侧幂等；重发次数由 job max_attempts 兜底（有界）。
                return self._precheck_and_send(
                    ctx, job, row, provider, probe, row.attempt_count, provider_key
                )
            raise self._delivery_failed(
                row.id, row.attempt_count, "failed" if last_attempt else "unknown",
                "delivery_unknown", "receipt not found after crash", retryable=True,
            )
        raise self._delivery_failed(
            row.id, row.attempt_count, "failed" if last_attempt else "unknown",
            "receipt_query_failed", f"unknown receipt kind {receipt.kind}", retryable=True,
        )

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
            # 失败路径不独立提交 T10；收敛计划交给 D 的同事务 callback。探针在
            # `_recheck_and_mark` 置 sending **之前**执行，T10 attempt_count 仍是
            # `row.attempt_count`（未被本次递增），故收敛代次用旧值，否则守卫失配。
            raise self._delivery_failed(
                row.id, row.attempt_count, "failed" if last_attempt else "unknown",
                "session_unverified", type(exc).__name__, retryable=True,
            ) from exc
        if verified_snapshot is None:
            # 探针否定：仍进入短事务重检，由重检判定并 cancelled（不直接发送）。
            log.info("notification.session_unverified", extra={"notificationId": row.id})
        if ctx.abort_event.is_set():
            return None

        # 5. 短事务重检 + 置 sending（提交后才发送）；把锁外快照带入锁内复核，
        #    封堵"核验之后、加锁之前"目标被改写的 TOCTOU 窗口。绑定不符由
        #    _recheck_and_mark 抛出（不写 T10），路由不符返回 cancelled。
        outcome = self._recheck_and_mark(
            ctx.engine, job, row, new_attempt, verified_snapshot
        )
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
            # provider 异常不臆断通道事实；失败路径不独立提交 T10。
            raise self._delivery_failed(
                row.id, new_attempt, "failed" if last_attempt else "unknown",
                "provider_transient", type(exc).__name__, retryable=True,
            ) from exc
        if ctx.abort_event.is_set():
            return None

        if result.kind == KIND_ACCEPTED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    job, row.id, new_attempt, "submitted", result.provider_message_id, None
                )
            )
        if result.kind == KIND_DELIVERED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    job, row.id, new_attempt, "delivered", result.provider_message_id, None
                )
            )
        if result.kind == KIND_REJECTED:
            return HandlerResult(
                business_tx=self._finalize_tx(
                    job, row.id, new_attempt, "failed", None,
                    _error("provider_rejected", result.reason or "provider rejected",
                           retryable=False),
                )
            )
        if result.kind == KIND_UNKNOWN:
            # 通道结果不确定：绝不把 T10 置"终态且 T12 成功"、断掉对账链；失败路径不
            # 独立提交 T10，T10 保持 sending/unknown 由下一次领取对账（收敛计划待 D）。
            raise self._delivery_failed(
                row.id, new_attempt, "failed" if last_attempt else "unknown",
                "delivery_unknown", result.reason or "delivery unknown", retryable=True,
            )
        if result.kind == KIND_TRANSIENT:
            raise self._delivery_failed(
                row.id, new_attempt, "failed" if last_attempt else "unknown",
                "provider_transient", result.reason or "provider transient", retryable=True,
            )
        raise self._delivery_failed(
            row.id, new_attempt, "failed" if last_attempt else "unknown",
            "provider_transient", f"unknown outcome kind {result.kind}", retryable=True,
        )

    # ---------------- short transactional re-check ----------------

    @dataclass
    class _Recheck:
        cancelled: bool
        reason: Optional[str] = None
        registration: Optional[dict[str, Any]] = None

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

            # Oracle #5 防御性复校（handle 已前置）：身份绑定不符绝不投递，且**不写 T10**
            # （raise 使本重检事务整体回滚），收敛计划随 DeliveryFailed 交给 D 的 callback。
            binding = self._classify_binding(job, row.id, int(t10["destination_revision"]))
            if binding is not None and binding[0] == _BINDING_UNSUPPORTED:
                # 置 sending 的 UPDATE 尚未执行（本事务随 raise 回滚），T10 代次仍是
                # `row.attempt_count`；收敛代次与之对齐，否则守卫失配成 no-op。
                raise self._delivery_failed(
                    row.id, row.attempt_count, "failed",
                    "UNSUPPORTED_CONTRACT", binding[1], retryable=False,
                )

            # 先比对锁外快照与锁内事实（TOCTOU），再比对 T10 快照代次。
            reason: Optional[str] = None
            if binding is not None and binding[0] == _BINDING_ROUTE_EXPIRED:
                reason = binding[1]
            if reason is None:
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
    def _classify_binding(
        job: Optional[JobRow], notification_id: str, destination_revision: int
    ) -> Optional[tuple[str, str]]:
        """复核 T12 任务行与 T10 的业务绑定（Oracle #5）。

        返回 ``(kind, reason)``；``kind`` ∈ ``{_BINDING_UNSUPPORTED,
        _BINDING_ROUTE_EXPIRED}``；全部相符返回 ``None``。

        字段来源：``owner_type``/``owner_id``/``input_revision``/``dedup_key`` 全部来自
        ``claim_batch`` 的 :class:`JobRow` 行投影（A 的 ``_SELECT_CLAIMABLE`` 显式列出）；
        ``destination_revision`` 由调用方传入——``handle()`` 用 T10 行快照，
        最终写回事务内用单表重读的最新值（两次都要校验；禁 JOIN）。
        """
        if job is None:
            return (_BINDING_UNSUPPORTED, "missing_job_binding")
        if job.job_type != JOB_TYPE:
            return (_BINDING_UNSUPPORTED, "job_type_mismatch")
        if job.owner_type != "notification":
            return (_BINDING_UNSUPPORTED, "owner_type_mismatch")
        try:
            same_owner = uuid.UUID(str(job.owner_id)) == uuid.UUID(str(notification_id))
        except (ValueError, AttributeError, TypeError):
            same_owner = False
        if not same_owner:
            return (_BINDING_UNSUPPORTED, "owner_id_mismatch")
        if job.dedup_key != f"notification:{notification_id}":
            return (_BINDING_UNSUPPORTED, "dedup_key_mismatch")
        # input_revision 语义 = destination_revision（路由快照即业务输入）。T10 行创建后
        # 该列不可变；若入队后路由代次被合法推进，则视为过期路由，按发送前重检取消。
        if int(job.input_revision) != int(destination_revision):
            return (_BINDING_ROUTE_EXPIRED, "input_revision_stale")
        return None

    @staticmethod
    def _delivery_failed(
        notification_id: str,
        attempt: int,
        status: str,
        code: str,
        reason: str,
        *,
        retryable: bool,
    ) -> "DeliveryFailed":
        """构造携带 T10 收敛计划的失败（**不在此处写 T10**，见 Oracle #6）。

        ``status`` 同时是终态判据：``'failed'``（永久失败或末次）→ 计划随
        ``business_tx`` 同事务收敛；``'unknown'``（非末次）→ 不收敛、T10 可观测。
        ``attempt`` 必须是 T10 当前 ``attempt_count``：已置 sending 的路径用本次新
        attempt，未置 sending（探针异常/绑定不符）的路径用读到的旧值。
        """
        return DeliveryFailed(
            code,
            reason,
            retryable=retryable,
            convergence=T10Convergence(
                notification_id=notification_id,
                attempt=attempt,
                status=status,
                last_error=_error(code, reason, retryable=retryable),
            ),
        )

    def _cancel_t10(
        self, engine: Engine, notification_id: str, attempt: int, reason: str
    ) -> bool:
        """路由过期（``input_revision`` 滞后于 T10 代次）的发送前取消。

        ``cancelled`` 是"未发送"的安全决定（不是已发布投递结果），沿用发送前重检的
        既有语义与守卫；带 ``attempt_count`` 守卫以免覆盖并发新代次事实。
        """
        with engine.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE notifications SET status = 'cancelled',"
                    " last_error = CAST(:err AS jsonb), updated_at = now()"
                    " WHERE id = :nid AND attempt_count = :att"
                    " AND status NOT IN ('submitted','delivered','cancelled','failed')"
                ),
                {"err": json.dumps(_error("route_recheck_failed", reason, retryable=False)),
                 "nid": notification_id, "att": attempt},
            )
            return res.rowcount > 0

    def _recheck_binding_in_tx(
        self, conn: Connection, job: Optional[JobRow], notification_id: str
    ) -> None:
        """Oracle #5：最终写回事务内复校 T12/T10 绑定。

        不符 → 抛 :class:`StaleNotification` 使整个业务写（含 T10 写）回滚，绝不发布；
        回收器/下一次领取将以入口校验按既有语义终结。禁 JOIN、单表读取。
        """
        m = conn.execute(
            text("SELECT destination_revision FROM notifications WHERE id = :nid"),
            {"nid": notification_id},
        ).first()
        if m is None:
            raise StaleNotification(
                f"notification {notification_id} missing on finalize binding recheck"
            )
        binding = self._classify_binding(job, notification_id, int(m[0]))
        if binding is not None:
            raise StaleNotification(
                f"notification {notification_id} binding changed before finalize:"
                f" {binding[0]}/{binding[1]}"
            )

    # ---------------- final business writes ----------------

    def _finalize_tx(
        self,
        job: Optional[JobRow],
        notification_id: str,
        attempt: int,
        status: str,
        provider_message_id: Optional[str],
        last_error: Optional[dict[str, Any]],
    ):
        def tx(conn: Connection) -> None:
            # Oracle #5：最终写回事务内复校绑定；不符 → raise 使 T10/T12 写整体回滚。
            self._recheck_binding_in_tx(conn, job, notification_id)
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
        job: Optional[JobRow],
        notification_id: str,
        attempt: int,
        status: str,
        provider_message_id: Optional[str],
        last_error: Optional[dict[str, Any]],
    ):
        """对账收敛写回：T10 可能停在 ``sending``（崩溃）或 ``unknown``（结果不确定）。"""

        def tx(conn: Connection) -> None:
            # Oracle #5：最终写回事务内复校绑定；不符 → 不写、整体回滚。
            self._recheck_binding_in_tx(conn, job, notification_id)
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


def _converge_plan_tx(plan: T10Convergence) -> "Callable[[Connection], None]":
    """把失败收敛计划包装成 D 的 ``complete_failure`` 同事务 ``business_tx``。

    仅做 T10 字段级 UPDATE（禁网络）；守卫 0 行返回 ``False``（幂等 no-op，不抛异常），
    由 ``complete_failure`` 的 T12 守卫决定是否整体回滚。
    """

    def tx(conn: Connection) -> None:
        converge_t10_tx(
            conn, plan.notification_id, plan.attempt, plan.status, plan.last_error
        )

    return tx


def converge_t10_tx(
    conn: Connection,
    notification_id: str,
    attempt: int,
    status: str,
    last_error: dict[str, Any],
) -> bool:
    """在给定 connection 上字段级收敛 T10（**供 D 的失败完成事务回调同事务调用**）。

    纯函数式、幂等：仅在 T10 仍处**非终态**且 ``attempt_count`` == 本次代次时更新；
    旧尝试/已终态绝不覆盖新事实，不匹配时返回 ``False``（no-op，不抛异常）。供 D 的
    ``complete_failure(..., business_tx=...)`` 与 T12 lease 守卫写放进同一
    ``engine.begin()`` 事务；守卫 0 行时由该事务整体回滚业务写。

    **守卫说明**：失败收敛的守卫是 ``status NOT IN 终态`` + ``attempt_count=本次``
    （``_cancel_t10`` 同族谓词）。这是为了覆盖"从未发送过"的终态失败——绑定身份不符、
    probe 异常、``provider_not_configured`` 等路径 T10 仍为 ``pending``，必须在 T12
    终态化的同一事务里一并收敛，避免无后续领取时滞留（lane-m5 必测 14）。成功写回
    （``_finalize_tx``/``_reconcile_finalize_tx``）仍严格守卫 ``status IN
    ('sending','unknown')``，绝不从 ``pending`` 发布投递结果。

    :param conn: 与 T12 守卫写同一事务的 SQLAlchemy Connection
    :param notification_id: T10 主键（= T12 ``owner_id``，由 payload 派生）
    :param attempt: 本次尝试的 T10 ``attempt_count``（代次守卫）
    :param status: 收敛目标状态（``failed`` / ``unknown``）
    :param last_error: 有界 ``last_error`` dict（``code``/``reason``/``retryable``）
    :return: 是否实际更新（``False`` = 幂等 no-op）
    """
    res = conn.execute(
        text(
            "UPDATE notifications SET status = :st,"
            " last_error = CAST(:err AS jsonb), updated_at = now()"
            " WHERE id = :nid"
            " AND status NOT IN ('submitted','delivered','cancelled','failed')"
            " AND attempt_count = :att"
        ),
        {"st": status, "err": json.dumps(last_error), "nid": notification_id,
         "att": attempt},
    )
    return res.rowcount > 0


handler = NotificationDeliverHandler()

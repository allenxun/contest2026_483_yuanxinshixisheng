"""推送通道端口 + 明确命名的 dev/test 替身（C4；推送通道未选定）。

- 端口 :class:`PushProvider`：``deliver``（锁外发送）+ ``query_receipt``（崩溃后对账）。
- 替身 :class:`DevTestDoublePushProvider`：可配置产生四态
  ``accepted/delivered/rejected/unknown``，并可配置回执
  ``accepted/delivered/not_found``；记录调用以供测试断言"不误发"。
- 生产 fail-closed：``app.env=production`` 且无真实 provider 配置时
  :func:`build_push_provider` 立即抛错，绝不默认放行（本 MVP 未实现真实 provider）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from .config import NotificationSettings

# 投递结果种类（T10.status 由 handler 映射）
KIND_ACCEPTED = "accepted"      # 可信受理 ID → submitted
KIND_DELIVERED = "delivered"    # 可信送达回执 → delivered
KIND_REJECTED = "rejected"      # 永久失败 → failed
KIND_TRANSIENT = "transient"    # 明确未受理的瞬时失败 → 退避重试
KIND_UNKNOWN = "unknown"        # 超时/不确定 → unknown，不盲目重发

# 回执查询结果种类
RECEIPT_ACCEPTED = "accepted"
RECEIPT_DELIVERED = "delivered"
RECEIPT_NOT_FOUND = "not_found"

_DELIVER_MODES = frozenset(
    {KIND_ACCEPTED, KIND_DELIVERED, KIND_REJECTED, KIND_TRANSIENT, KIND_UNKNOWN}
)
_RECEIPT_MODES = frozenset({RECEIPT_ACCEPTED, RECEIPT_DELIVERED, RECEIPT_NOT_FOUND})


@dataclass(frozen=True)
class PushOutcome:
    kind: str
    provider_message_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ReceiptOutcome:
    kind: str
    provider_message_id: str | None = None


@dataclass
class PushCall:
    """替身记录的一次发送（供测试断言内容合规与调用次数）。"""

    provider_message_key: str
    text: str
    registration: Mapping[str, Any]


@runtime_checkable
class PushProvider(Protocol):
    def deliver(
        self, *, registration: Mapping[str, Any], text: str, provider_message_key: str
    ) -> PushOutcome: ...

    def query_receipt(self, provider_message_key: str) -> ReceiptOutcome: ...


class DevTestDoublePushProvider:
    """明确命名的 dev/test 替身——**不代表生产可用**。"""

    def __init__(self, *, mode: str = KIND_ACCEPTED, receipt_mode: str = RECEIPT_NOT_FOUND) -> None:
        if mode not in _DELIVER_MODES:
            raise ValueError(f"unknown push double mode: {mode}")
        if receipt_mode not in _RECEIPT_MODES:
            raise ValueError(f"unknown push receipt mode: {receipt_mode}")
        self.mode = mode
        self.receipt_mode = receipt_mode
        self.calls: list[PushCall] = []
        self.receipt_queries: list[str] = []

    # 测试辅助
    def set_mode(self, mode: str) -> None:
        if mode not in _DELIVER_MODES:
            raise ValueError(f"unknown push double mode: {mode}")
        self.mode = mode

    def set_receipt_mode(self, receipt_mode: str) -> None:
        if receipt_mode not in _RECEIPT_MODES:
            raise ValueError(f"unknown push receipt mode: {receipt_mode}")
        self.receipt_mode = receipt_mode

    def deliver(
        self, *, registration: Mapping[str, Any], text: str, provider_message_key: str
    ) -> PushOutcome:
        self.calls.append(
            PushCall(provider_message_key=provider_message_key, text=text, registration=registration)
        )
        if self.mode == KIND_ACCEPTED:
            return PushOutcome(KIND_ACCEPTED, provider_message_id=f"acc-{provider_message_key}")
        if self.mode == KIND_DELIVERED:
            return PushOutcome(KIND_DELIVERED, provider_message_id=f"dlv-{provider_message_key}")
        if self.mode == KIND_REJECTED:
            return PushOutcome(KIND_REJECTED, reason="provider_rejected")
        if self.mode == KIND_TRANSIENT:
            return PushOutcome(KIND_TRANSIENT, reason="provider_transient")
        return PushOutcome(KIND_UNKNOWN, reason="delivery_unknown")

    def query_receipt(self, provider_message_key: str) -> ReceiptOutcome:
        self.receipt_queries.append(provider_message_key)
        if self.receipt_mode == RECEIPT_ACCEPTED:
            return ReceiptOutcome(RECEIPT_ACCEPTED, provider_message_id=f"acc-{provider_message_key}")
        if self.receipt_mode == RECEIPT_DELIVERED:
            return ReceiptOutcome(RECEIPT_DELIVERED, provider_message_id=f"dlv-{provider_message_key}")
        return ReceiptOutcome(RECEIPT_NOT_FOUND)


def build_push_provider(settings: NotificationSettings) -> PushProvider:
    """dev/test → 替身（env 配置四态）；production → fail-closed。

    本 MVP 没有真实推送供应商实现，因此生产一律拒绝，绝不默认放行。
    """
    if settings.production:
        configured = (os.environ.get("MVP_NOTIFY_PUSH_PROVIDER") or "").strip()
        raise RuntimeError(
            "no real PushProvider configured for production"
            f" (MVP_NOTIFY_PUSH_PROVIDER={configured!r}); refusing to send (fail closed)"
        )
    mode = os.environ.get("MVP_NOTIFY_PUSH_DOUBLE", KIND_ACCEPTED).strip() or KIND_ACCEPTED
    receipt_mode = (
        os.environ.get("MVP_NOTIFY_PUSH_RECEIPT", RECEIPT_NOT_FOUND).strip() or RECEIPT_NOT_FOUND
    )
    return DevTestDoublePushProvider(mode=mode, receipt_mode=receipt_mode)

"""face-service HTTP 传输抽象 + **通用**错误分类（phase 1：不绑定任何具体合同）。

**重要边界（2026-09-16 总协调/监督更正）**：本模块**不**把任何 face-service 路由名、
请求/响应 JSON 字段、HTTP 状态码或 ``errors.py`` 错误码表当作**已冻结的最终合同**。
仓库里可观察到的 face-service 代码不是 B 的交付基线；在总协调提供**显式的已提交 B
face-service SHA + Oracle 审查 SHA** 之前，任何“code → (status, retryable)”逐码绑定、
跨语言合同测试都属于禁止事项（详见
``.mvp-d-runtime/waiting-dependency-insightface.md``）。

因此本模块只提供**与具体供应商合同无关**的传输 seam 与分类策略：

- :class:`FaceServiceTransport` / :class:`TransportResult`：纯形状协议；
- :func:`classify_face_response`：只依赖**通用 HTTP 语义**（2xx 成功；401/403 鉴权；
  5xx/408/429 可重试；其余 4xx 终态）与信封里**调用方自己声明**的 ``retryable`` 布尔；
- :class:`FakeTransport`：纯内存替身（单测用，零网络）；
- :class:`SealedHttpTransport`：phase-2 seam 占位，一调用即 fail-closed。

phase 2（合同冻结后）才允许：真实 HTTP 客户端、逐码 → Worker 语义映射表、跨语言合同
测试、以及 live error-mapping 回归。

Worker 语义约定（与既有 handler 错误路径一致）：

- 可重试 → 既有 ``ProviderUnavailable`` → ``DEPENDENCY_UNAVAILABLE``（退避重排、attempt 上限）；
- 非重试 → 终态分类；
- 鉴权失败（HTTP 401/403）→ 配置型终态。

**绝不**静默成功、**绝不**回退 ``double`` 替身、**绝不**把分数当活体结论。
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

# ------------------------------------------------------------------ result


@dataclass(frozen=True)
class TransportResult:
    """一次外部调用的原始结果（已解析 JSON；未解析则为 ``None``）。"""

    status: int
    json: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class FaceServiceTransport(Protocol):
    """传输协议：adapter 只依赖它；测试注入 :class:`FakeTransport`。

    方法名与参数是 Worker 内部 seam，**不是** face-service 的 HTTP 合同；phase 2 才把
    ``method``/``path``/``json_body`` 映射到经 B 书面确认的真实路由。
    """

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        headers_extra: Optional[Mapping[str, str]] = None,
    ) -> TransportResult: ...


# ------------------------------------------------------------------ error classification


class TransportErrorClass(str, enum.Enum):
    """Worker 侧错误分类（三类；由通用 HTTP 语义 + 调用方声明的 retryable 派生）。"""

    RETRYABLE = "retryable"
    TERMINAL = "terminal"
    AUTH_CONFIG = "auth_config"


#: 通用鉴权失败状态码（HTTP 语义，**非** face-service 合同细节）。
AUTH_HTTP_STATUSES = frozenset({401, 403})
#: 通用“值得退避重试”的状态码（HTTP 语义）。
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429})


class FaceServiceTransportError(RuntimeError):
    """传输/服务错误基类（不携带任何 secret；消息只含 code/status/request_id）。"""


class FaceServiceDependencyError(FaceServiceTransportError):
    """可重试依赖不可用 → 既有 ``ProviderUnavailable`` / ``DEPENDENCY_UNAVAILABLE``。"""

    retryable = True


class FaceServiceTerminalError(FaceServiceTransportError):
    """非重试终态错误 → phase 2 映射到终态分类。"""

    retryable = False


class FaceServiceAuthConfigError(FaceServiceTerminalError):
    """鉴权/配置失败（HTTP 401/403）→ 配置型终态。"""


def _error_envelope(body: Any) -> Optional[Mapping[str, Any]]:
    """取出 ``{"error": {...}}`` 信封；形状不合则 ``None``（不猜其它字段名）。"""
    if not isinstance(body, Mapping):
        return None
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None
    return error


def classify_face_error_body(body: Any) -> Optional[TransportErrorClass]:
    """只依据信封里**调用方自己声明**的 ``retryable`` 布尔分类。

    - ``retryable is True`` → 可重试；``retryable is False`` → 终态；
    - 缺 ``retryable`` / 非布尔 → ``None``（交给 :func:`classify_face_response` 的
      通用状态码兜底）；**绝不**按 code 名称猜测可重试性。
    """
    error = _error_envelope(body)
    if error is None:
        return None
    retryable = error.get("retryable")
    if retryable is True:
        return TransportErrorClass.RETRYABLE
    if retryable is False:
        return TransportErrorClass.TERMINAL
    return None


def classify_face_response(status: int, body: Any) -> Optional[TransportErrorClass]:
    """完整响应分类：2xx → ``None``（成功）；否则信封 retryable 优先，状态码兜底。

    全部依据**通用 HTTP 语义**，不依赖任何未冻结的错误码表。
    """
    status = int(status)
    if 200 <= status < 300:
        return None
    if status in AUTH_HTTP_STATUSES:
        return TransportErrorClass.AUTH_CONFIG
    classified = classify_face_error_body(body)
    if classified is not None:
        return classified
    if status >= 500 or status in RETRYABLE_HTTP_STATUSES:
        return TransportErrorClass.RETRYABLE
    return TransportErrorClass.TERMINAL


def error_code_from_body(body: Any) -> Optional[str]:
    """只读信封里的 ``error.code`` 字符串（用于日志/异常消息；**不**用于分类决策）。"""
    error = _error_envelope(body)
    if error is None:
        return None
    code = error.get("code")
    return code if isinstance(code, str) and code else None


def raise_for_face_response(
    status: int, body: Any, *, request_id: Optional[str] = None
) -> None:
    """非 2xx 即抛类型化传输错误；消息只含安全标量（code/status/request_id）。"""
    classified = classify_face_response(status, body)
    if classified is None:
        return
    code = error_code_from_body(body)
    rid = f" request_id={request_id}" if request_id else ""
    label = f"code={code}" if code else "body=unclassified"
    message = f"face-service rejected request (status={status}, {label}){rid}"
    if classified is TransportErrorClass.RETRYABLE:
        raise FaceServiceDependencyError(message)
    if classified is TransportErrorClass.AUTH_CONFIG:
        raise FaceServiceAuthConfigError(message)
    raise FaceServiceTerminalError(message)


# ------------------------------------------------------------------ fake transport


class FakeTransport:
    """纯内存传输替身：按序返回预置结果并记录调用；零网络、零合同假设。"""

    def __init__(
        self,
        responses: Optional[list[TransportResult]] = None,
        *,
        default_result: Optional[TransportResult] = None,
    ) -> None:
        self._responses = list(responses or [])
        self._default_result = default_result
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        headers_extra: Optional[Mapping[str, str]] = None,
    ) -> TransportResult:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "json_body": dict(json_body) if json_body is not None else None,
                "headers_extra": dict(headers_extra) if headers_extra is not None else None,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        if self._default_result is not None:
            return self._default_result
        raise FaceServiceDependencyError(
            "FakeTransport: no queued response (test must enqueue one)"
        )


# ------------------------------------------------------------------ phase-2 seam


class SealedHttpTransport:
    """phase-2 seam：真实 HTTP 客户端的占位（**尚未实现**，一调用即 fail-closed）。

    - 构造时由 caller 传入已校验的 token（见 :func:`dtokenfile.read_token_file`，
      read-once-at-construction、不缓存）；本类只保存，``__repr__`` 脱敏，绝不落日志；
    - ``request`` 抛可重试 :class:`FaceServiceDependencyError`（绝不伪造成功，绝不回退
      替身）；phase 2 在**同一构造签名**与 :class:`FaceServiceTransport` 协议下替换为
      真实客户端，并把 ``method``/``path`` 绑定到经 B 书面确认的路由。
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        connect_timeout_ms: int,
        read_timeout_ms: int,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._connect_timeout_ms = int(connect_timeout_ms)
        self._read_timeout_ms = int(read_timeout_ms)

    @property
    def base_url(self) -> str:
        return self._base_url

    def has_token(self) -> bool:
        """是否存在 token（只回答布尔，绝不返回取值）。"""
        return bool(self._token)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        headers_extra: Optional[Mapping[str, str]] = None,
    ) -> TransportResult:
        raise FaceServiceDependencyError(
            "face-service HTTP client is not bound yet (phase 2); "
            "real transport is intentionally not implemented"
        )

    def __repr__(self) -> str:  # noqa: D105 - 脱敏
        return (
            f"SealedHttpTransport(base_url={self._base_url!r}, token='<redacted>', "
            f"connect_timeout_ms={self._connect_timeout_ms}, "
            f"read_timeout_ms={self._read_timeout_ms})"
        )


def parse_json_bytes(raw: Any) -> Any:
    """辅助：把 bytes/str 解析为 JSON；失败返回 ``None``（调用方决定分类）。"""
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


__all__ = [
    "TransportResult",
    "FaceServiceTransport",
    "TransportErrorClass",
    "AUTH_HTTP_STATUSES",
    "RETRYABLE_HTTP_STATUSES",
    "FaceServiceTransportError",
    "FaceServiceDependencyError",
    "FaceServiceTerminalError",
    "FaceServiceAuthConfigError",
    "classify_face_error_body",
    "classify_face_response",
    "error_code_from_body",
    "raise_for_face_response",
    "FakeTransport",
    "SealedHttpTransport",
    "parse_json_bytes",
]
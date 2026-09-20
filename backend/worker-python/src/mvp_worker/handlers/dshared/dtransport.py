"""face-service HTTP 传输 + 冻结错误码表 + 真实 stdlib 客户端（phase 2）。

**权威来源**：``backend/handoffs/B-face-service-worker-contract.md``（冻结合同，
最终代码 SHA ``bec9eb97``，Oracle r31 PASS-with-notes）。本模块只做传输与分类，
不做业务决策；业务映射在 :mod:`providers` 的 ``InsightFaceAdapter``。

冻结错误码表 :data:`FACE_ERROR_SPECS` 逐条镜像合同 §7 的 18 个码
（``code -> (http_status, retryable)``）；单测用**合同 §7 的字面清单**双向比对，
不 import B 的 ``errors.py``（跨服务不耦合）。

传输纪律（合同 §7/§8）：

- 鉴权头 ``X-Internal-Token`` 由 :func:`dtokenfile.read_token_file` 以 0600 文件读入，
  **绝不**出现在异常、日志、repr；
- 每次调用生成 ``X-Request-Id``（uuid4 hex）；服务端合法回显、否则自行生成；
- connect / read 分别按 config 超时（stdlib ``http.client``；``urllib.request`` 底层
  亦为它，但只暴露单一 socket 超时，无法分别表达两段）；
- 异常消息只含 **method / status / code / request_id 标量**，**不含** token、图片字节、
  embedding、namespace/subject_id/correlation_id 取值（路由模板纪律）；
- **不记录** ``details`` 内容（可能含调用方传入的标识；分类只用 code/status/retryable）。
"""
from __future__ import annotations

import http.client
import json
import socket
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

# ------------------------------------------------------------------ result


@dataclass(frozen=True)
class TransportResult:
    """一次 face-service 调用的原始结果（已解析 JSON；必然为 dict）。"""

    status: int
    json: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class FaceServiceTransport(Protocol):
    """传输协议：adapter 只依赖它；测试注入 :class:`FakeTransport`。"""

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        headers_extra: Optional[Mapping[str, str]] = None,
    ) -> TransportResult: ...


# ------------------------------------------------------------------ frozen error table


#: 合同 §7 冻结的 18 个错误码 → ``(http_status, retryable)``。
#: **双向锁定**：单测以合同字面清单比对（不 import B 源码）。改动前必须先改合同。
FACE_ERROR_SPECS: dict[str, tuple[int, bool]] = {
    "NO_FACE": (400, False),
    "MULTI_FACES_AMBIGUOUS": (400, False),
    "IMAGE_DECODE_FAILED": (400, False),
    "INVALID_REQUEST": (400, False),
    "UNAUTHORIZED": (401, False),
    "SUBJECT_NOT_FOUND": (404, False),
    "NAMESPACE_NOT_FOUND": (404, False),
    "SUBJECT_ALREADY_EXISTS": (409, False),
    "IMAGE_TOO_LARGE": (413, False),
    "UNSUPPORTED_MEDIA_TYPE": (415, False),
    "QUALITY_INSUFFICIENT": (422, False),
    "LIVENESS_UNSUPPORTED": (501, False),
    "INTERNAL_ERROR": (500, True),
    "MODEL_UNAVAILABLE": (503, True),
    "MODEL_NOT_LOADED": (503, True),
    "STORE_UNAVAILABLE": (503, True),
    "CONCURRENCY_LIMIT": (429, True),
    "INFERENCE_TIMEOUT": (504, True),
}

#: 通用鉴权状态码（401/403 一律配置型终态）。
AUTH_HTTP_STATUSES = frozenset({401, 403})
#: 通用可重试状态码（无合法信封时的兜底）。
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429})


# ------------------------------------------------------------------ exceptions


class FaceServiceTransportError(RuntimeError):
    """传输/服务错误基类；消息只含安全标量，绝不携带 secret/标识取值。"""


class FaceServiceTimeout(FaceServiceTransportError):
    """客户端侧超时（连接或读取）。register 据此映射 ``timeout`` 并对账。"""


class FaceServiceConnectionError(FaceServiceTransportError):
    """连接层失败（拒绝/DNS/重置/中断）→ 传输不确定。"""


class FaceServiceProtocolError(FaceServiceTransportError):
    """2xx 但响应不是合法 JSON object（结构与语义校验由 adapter 负责）。"""


class FaceServiceHttpError(FaceServiceTransportError):
    """服务端返回非 2xx：解析统一错误信封后携带稳定标量。"""

    def __init__(
        self,
        *,
        status: int,
        code: Optional[str],
        retryable: bool,
        request_id: Optional[str] = None,
    ) -> None:
        label = code if code else "unclassified"
        rid = f" request_id={request_id}" if request_id else ""
        super().__init__(
            f"face-service rejected request (status={status}, code={label}){rid}"
        )
        self.status = status
        self.code = code
        self.retryable = retryable
        self.request_id = request_id

    @property
    def is_auth(self) -> bool:
        """401/403 或 ``UNAUTHORIZED`` → 配置型终态。"""
        return self.status in AUTH_HTTP_STATUSES or self.code == "UNAUTHORIZED"


# ------------------------------------------------------------------ parsing / classification


def parse_json_bytes(raw: Any) -> Any:
    """把 bytes/str 解析为 JSON；失败返回 ``None``（调用方决定分类）。"""
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return raw
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def error_envelope_fields(body: Any) -> tuple[Optional[str], Optional[bool], Optional[str]]:
    """取信封 ``error`` 的 ``(code, retryable, request_id)``；形状不合则 None。

    只读这三个标量；**不读取、不记录** ``details``（可能含调用方传入的标识）。
    """
    if not isinstance(body, Mapping):
        return None, None, None
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None, None, None
    raw_code = error.get("code")
    code = raw_code if isinstance(raw_code, str) and raw_code else None
    raw_retryable = error.get("retryable")
    retryable = raw_retryable if isinstance(raw_retryable, bool) else None
    raw_rid = error.get("request_id")
    request_id = raw_rid if isinstance(raw_rid, str) and raw_rid else None
    return code, retryable, request_id


def classify_error(
    status: int, body: Any, *, response_request_id: Optional[str] = None
) -> tuple[Optional[str], bool]:
    """非 2xx 的分类：冻结表优先，其次信封 ``retryable``，最后状态码兜底。"""
    code, envelope_retryable, envelope_rid = error_envelope_fields(body)
    if code is not None and code in FACE_ERROR_SPECS:
        return code, FACE_ERROR_SPECS[code][1]
    if envelope_retryable is not None:
        return code, envelope_retryable
    del envelope_rid, response_request_id  # 仅用于异常消息，不参与分类
    return code, (int(status) >= 500 or int(status) in RETRYABLE_HTTP_STATUSES)


# ------------------------------------------------------------------ header builder


def request_headers(
    token: str, *, request_id: Optional[str] = None
) -> dict[str, str]:
    """构造出站头：鉴权 + 每调用一个 ``X-Request-Id``（默认新 uuid4 hex）。"""
    return {
        "X-Internal-Token": token,
        "X-Request-Id": request_id or uuid.uuid4().hex,
        "Accept": "application/json",
    }


# ------------------------------------------------------------------ real stdlib client


class StdlibHttpTransport:
    """真实 stdlib HTTP 客户端（``http.client``；无新增依赖）。

    用 ``http.client`` 而非 ``urllib.request`` 的唯一原因是**分别**执行 connect 与 read
    超时（``urlopen`` 只暴露单一 socket 超时）。connect 超时在 ``connect()`` 阶段生效，
    随后把同一 socket 的读超时切到 ``read_timeout_ms``。

    token 由构造方经 0600 文件读入后传入；本类只持有，``__repr__`` 脱敏。
    出站请求绝不包含 ``require_liveness`` / 阈值 / ``on_exists``（由 adapter 保证）。
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        connect_timeout_ms: int,
        read_timeout_ms: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._connect_timeout = max(1, int(connect_timeout_ms)) / 1000.0
        self._read_timeout = max(1, int(read_timeout_ms)) / 1000.0
        parsed = urlparse(self._base_url)
        self._scheme = (parsed.scheme or "http").lower()
        self._host = parsed.hostname or ""
        self._port = parsed.port or (443 if self._scheme == "https" else 80)
        self._base_path = parsed.path.rstrip("/")

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
        if not self._host:
            raise FaceServiceConnectionError("face-service base URL has no host")
        headers = request_headers(self._token)
        body: Optional[bytes] = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if headers_extra:
            headers.update(headers_extra)
        full_path = f"{self._base_path}{path}"

        conn_cls = (
            http.client.HTTPSConnection
            if self._scheme == "https"
            else http.client.HTTPConnection
        )
        try:
            conn = conn_cls(self._host, self._port, timeout=self._connect_timeout)
            try:
                conn.connect()
                # 连接已建立：切换到读超时（服务端推理可能耗时，见合同 §7）。
                if conn.sock is not None:
                    conn.sock.settimeout(self._read_timeout)
                conn.request(method, full_path, body=body, headers=headers)
                response = conn.getresponse()
                status = int(response.status)
                response_headers = {
                    str(k).lower(): str(v) for k, v in response.getheaders()
                }
                raw = response.read()
            finally:
                conn.close()
        except (socket.timeout, TimeoutError) as exc:
            raise FaceServiceTimeout("face-service request timed out") from exc
        except (ConnectionError, OSError) as exc:
            raise FaceServiceConnectionError(
                f"face-service connection failed ({type(exc).__name__})"
            ) from exc

        parsed_body = parse_json_bytes(raw)
        if 200 <= status < 300:
            if not isinstance(parsed_body, dict):
                raise FaceServiceProtocolError(
                    "face-service 2xx response is not a JSON object"
                )
            return TransportResult(status, parsed_body, response_headers)

        code, retryable = classify_error(status, parsed_body)
        _, _, envelope_rid = error_envelope_fields(parsed_body)
        request_id = envelope_rid or response_headers.get("x-request-id")
        raise FaceServiceHttpError(
            status=status, code=code, retryable=retryable, request_id=request_id
        )

    def __repr__(self) -> str:  # noqa: D105 - 脱敏
        return (
            f"StdlibHttpTransport(base_url={self._base_url!r}, token='<redacted>', "
            f"connect_timeout_ms={int(self._connect_timeout * 1000)}, "
            f"read_timeout_ms={int(self._read_timeout * 1000)})"
        )


# ------------------------------------------------------------------ fake transport


class FakeTransport:
    """纯内存传输替身：按序返回预置结果/抛出预置异常并记录调用；零网络。

    ``responses`` 元素可为 :class:`TransportResult`（返回）或 ``Exception``（抛出），
    便于错误映射矩阵测试。
    """

    def __init__(
        self,
        responses: Optional[list[Any]] = None,
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
            item = self._responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        if self._default_result is not None:
            return self._default_result
        raise FaceServiceTransportError(
            "FakeTransport: no queued response (test must enqueue one)"
        )


__all__ = [
    "TransportResult",
    "FaceServiceTransport",
    "FACE_ERROR_SPECS",
    "AUTH_HTTP_STATUSES",
    "RETRYABLE_HTTP_STATUSES",
    "FaceServiceTransportError",
    "FaceServiceTimeout",
    "FaceServiceConnectionError",
    "FaceServiceProtocolError",
    "FaceServiceHttpError",
    "parse_json_bytes",
    "error_envelope_fields",
    "classify_error",
    "request_headers",
    "StdlibHttpTransport",
    "FakeTransport",
]
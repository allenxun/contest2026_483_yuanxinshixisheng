"""Service-identity authentication and request-contract validation.

Internal routes accept a *service* identity only. End-user credentials are
rejected instead of forwarded, and no credential value is ever logged,
echoed back or handed to the model.
"""

from __future__ import annotations

import json
import re
import secrets
import uuid
from dataclasses import dataclass

from fastapi import Request
from pydantic import ValidationError

from rag.common.configuration import settings
from rag.common.utils import logger
from server.internal_ai.errors import InternalAiError
from server.internal_ai.models import IDENTIFIER_PATTERN, AiRequest

SERVICE_NAME_HEADER = "X-Service-Name"
API_KEY_HEADER = "X-API-Key"
REQUEST_ID_HEADER = "X-Request-Id"
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
PROTOCOL_VERSION_HEADER = "X-Protocol-Version"
TRACEPARENT_HEADER = "traceparent"
BUSINESS_DATA_GRANT_HEADER = "X-Business-Data-Grant"

# 内部接口只接受服务身份；携带终端用户凭证一律拒绝。
FORBIDDEN_HEADERS: tuple[str, ...] = ("Authorization", "Cookie", "Proxy-Authorization")

JSON_ACCEPT = "application/json"
STREAM_ACCEPT = "text/event-stream"

_IDENTIFIER = re.compile(IDENTIFIER_PATTERN)
# W3C Trace Context, version 00.
_TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
_MAX_LOGGED_HEADER = 64


@dataclass(frozen=True)
class ServiceCaller:
    """Authenticated calling service."""

    service_name: str


@dataclass(frozen=True)
class InvocationContext:
    """Correlation data of one accepted invocation.

    ``business_data_grant`` stays in memory for this call only: it is never
    logged, echoed in a response, persisted or placed in a prompt.
    """

    request_id: str
    idempotency_key: str
    traceparent: str
    invocation_id: str
    business_data_grant: str = ""


def get_internal_ai_config():
    """Dependency that exposes the deployed internal AI configuration."""
    return settings.internal_ai


def _constant_time_equals(provided: str, expected: str) -> bool:
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _clip(value: str) -> str:
    return " ".join((value or "").split())[:_MAX_LOGGED_HEADER]


def authenticate_service(request: Request, config) -> ServiceCaller:
    """Verify ``X-Service-Name`` plus ``X-API-Key``; fail closed.

    :raises InternalAiError: 400 for a forbidden credential header, 401 for a
        wrong or missing identity, 503 when the deployment configured no key.
    """
    for header in FORBIDDEN_HEADERS:
        if request.headers.get(header):
            # 只记录 Header 名，绝不记录它的值。
            logger.warning(
                "Rejected %s %s: %s header is not allowed",
                request.method,
                request.url.path,
                header,
            )
            raise InternalAiError(
                "AI_REQUEST_INVALID",
                f"内部 AI 接口不接受 {header} Header；请不要传递顾客或员工的登录凭证。",
            )

    allowed_service = (config.allowed_service or "").strip()
    service_name = (request.headers.get(SERVICE_NAME_HEADER) or "").strip()
    if not allowed_service:
        logger.error("internal_ai.allowed_service is empty; refusing all traffic.")
        raise InternalAiError(
            "AI_SERVICE_UNAVAILABLE", "AI 服务未登记允许的调用方，已拒绝全部请求。"
        )
    if not service_name or not _constant_time_equals(service_name, allowed_service):
        logger.warning(
            "Rejected %s %s: unauthorized X-Service-Name=%r",
            request.method,
            request.url.path,
            _clip(service_name),
        )
        raise InternalAiError("AI_UNAUTHORIZED", "X-Service-Name 缺失或未登记。")

    allowed_keys = config.get_api_keys()
    if not allowed_keys:
        logger.error(
            "internal_ai.api_keys is empty; refusing all traffic. "
            "Set APP_INTERNAL_AI_API_KEYS."
        )
        raise InternalAiError(
            "AI_SERVICE_UNAVAILABLE", "AI 服务未配置 X-API-Key，已拒绝全部请求。"
        )
    provided_key = (request.headers.get(API_KEY_HEADER) or "").strip()
    if not provided_key or not any(
        _constant_time_equals(provided_key, key) for key in allowed_keys
    ):
        logger.warning(
            "Rejected %s %s: %s",
            request.method,
            request.url.path,
            "no API key provided" if not provided_key else "invalid API key",
        )
        raise InternalAiError("AI_UNAUTHORIZED", "X-API-Key 缺失或无效。")

    return ServiceCaller(service_name)


def _validation_detail(exc: ValidationError) -> str:
    """Describe invalid fields without echoing any submitted value."""
    parts = []
    for error in exc.errors()[:5]:
        path = ".".join(str(item) for item in error.get("loc", ())) or "<body>"
        parts.append(f"{path}: {error.get('msg', 'invalid')}")
    suffix = "" if len(exc.errors()) <= 5 else f"（另有 {len(exc.errors()) - 5} 处错误）"
    return "请求正文不符合契约 -> " + "; ".join(parts) + suffix


async def read_invocation_payload(request: Request, config) -> AiRequest:
    """Read, size-check and validate the body, reporting errors as ProblemDetail."""
    body = await request.body()
    if len(body) > config.max_body_bytes:
        raise InternalAiError(
            "AI_PAYLOAD_TOO_LARGE",
            f"请求正文为 {len(body)} 字节，超过上限 {config.max_body_bytes} 字节。",
        )
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InternalAiError(
            "AI_REQUEST_INVALID", "请求正文必须是合法的 UTF-8 JSON 对象。"
        ) from exc
    try:
        return AiRequest.model_validate(raw)
    except ValidationError as exc:
        raise InternalAiError("AI_REQUEST_INVALID", _validation_detail(exc)) from exc


def _required_identifier(request: Request, header: str) -> str:
    value = (request.headers.get(header) or "").strip()
    if not value:
        raise InternalAiError("AI_REQUEST_INVALID", f"缺少必填 Header {header}。")
    if not _IDENTIFIER.fullmatch(value):
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            f"{header} 只能是 8~128 位的字母、数字或 . _ : - 字符。",
        )
    return value


def validate_invocation_headers(
    request: Request,
    payload: AiRequest,
    config,
    *,
    expect_accept: str,
) -> InvocationContext:
    """Check correlation, protocol version and Accept against the request body."""
    request_id = _required_identifier(request, REQUEST_ID_HEADER)
    if request_id != payload.request_id:
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            "X-Request-Id 与请求正文 request_id 不一致。",
            request_id=request_id,
        )
    idempotency_key = _required_identifier(request, IDEMPOTENCY_KEY_HEADER)

    expected_version = (config.protocol_version or "").strip()
    protocol_version = (request.headers.get(PROTOCOL_VERSION_HEADER) or "").strip()
    if protocol_version != expected_version:
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            f"X-Protocol-Version 必须为 {expected_version}。",
            request_id=request_id,
        )
    if payload.protocol_version != expected_version:
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            f"请求正文 protocol_version 必须为 {expected_version}，且与 Header 一致。",
            request_id=request_id,
        )

    traceparent = (request.headers.get(TRACEPARENT_HEADER) or "").strip()
    if not _TRACEPARENT.fullmatch(traceparent):
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            "traceparent 必须是合法的 W3C Trace Context（version 00）。",
            request_id=request_id,
        )

    accept = (request.headers.get("Accept") or "").strip()
    if expect_accept not in accept and "*/*" not in accept:
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            f"该路径的 Accept 必须包含 {expect_accept}。",
            request_id=request_id,
        )

    return InvocationContext(
        request_id=request_id,
        idempotency_key=idempotency_key,
        traceparent=traceparent,
        invocation_id=uuid.uuid4().hex,
        business_data_grant=(
            request.headers.get(BUSINESS_DATA_GRANT_HEADER) or ""
        ).strip(),
    )


def validate_service_headers(request: Request, config, *, expect_accept: str) -> InvocationContext:
    """Same Header 校验 as 问答接口，但不核对请求体里的 request_id。"""
    request_id = _required_identifier(request, REQUEST_ID_HEADER)
    idempotency_key = _required_identifier(request, IDEMPOTENCY_KEY_HEADER)
    expected_version = (config.protocol_version or "").strip()
    protocol_version = (request.headers.get(PROTOCOL_VERSION_HEADER) or "").strip()
    if protocol_version != expected_version:
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            f"X-Protocol-Version 必须为 {expected_version}。",
            request_id=request_id,
        )
    traceparent = (request.headers.get(TRACEPARENT_HEADER) or "").strip()
    if not _TRACEPARENT.fullmatch(traceparent):
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            "traceparent 必须是合法的 W3C Trace Context（version 00）。",
            request_id=request_id,
        )
    accept = (request.headers.get("Accept") or "").strip()
    if expect_accept not in accept and "*/*" not in accept:
        raise InternalAiError(
            "AI_REQUEST_INVALID",
            f"该路径的 Accept 必须包含 {expect_accept}。",
            request_id=request_id,
        )
    return InvocationContext(
        request_id=request_id,
        idempotency_key=idempotency_key,
        traceparent=traceparent,
        invocation_id=uuid.uuid4().hex,
        business_data_grant=(
            request.headers.get(BUSINESS_DATA_GRANT_HEADER) or ""
        ).strip(),
    )


async def read_json_object(request: Request, config) -> dict:
    body = await request.body()
    if len(body) > config.max_body_bytes:
        raise InternalAiError(
            "AI_PAYLOAD_TOO_LARGE",
            f"请求正文为 {len(body)} 字节，超过上限 {config.max_body_bytes} 字节。",
        )
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InternalAiError(
            "AI_REQUEST_INVALID", "请求正文必须是合法的 UTF-8 JSON 对象。"
        ) from exc
    if not isinstance(raw, dict):
        raise InternalAiError("AI_REQUEST_INVALID", "请求正文必须是 JSON 对象。")
    return raw



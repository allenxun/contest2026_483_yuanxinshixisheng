"""``AI_*`` error catalog and RFC 9457 ``application/problem+json`` responses.

The catalog is intentionally small: only codes this service can actually
produce are listed. ``AI_RESPONSE_INVALID`` belongs to the medical-platform
backend (the consumer), and ``AI_MCP_*`` / idempotency codes are not produced
until the corresponding capability is delivered.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi.responses import JSONResponse

from rag.common.utils import logger
from server.internal_ai.models import ProblemDetail

PROBLEM_CONTENT_TYPE = "application/problem+json"
ERROR_TYPE_PREFIX = "urn:aisia:ai:error:"


@dataclass(frozen=True)
class ErrorSpec:
    """One frozen ``AI_*`` code with its HTTP status and retry semantics."""

    code: str
    status: int
    title: str
    retryable: bool


ERROR_SPECS: dict[str, ErrorSpec] = {
    spec.code: spec
    for spec in (
        ErrorSpec("AI_REQUEST_INVALID", 400, "请求不符合冻结的接口契约", False),
        ErrorSpec("AI_UNAUTHORIZED", 401, "调用方服务身份未通过校验", False),
        ErrorSpec("AI_PAYLOAD_TOO_LARGE", 413, "请求正文超过允许的大小", False),
        ErrorSpec("AI_INTERNAL_ERROR", 500, "AI 服务内部错误", False),
        ErrorSpec("AI_SERVICE_UNAVAILABLE", 503, "AI 服务依赖未就绪", True),
        ErrorSpec("AI_UPSTREAM_TIMEOUT", 504, "AI 处理超过允许的时间", True),
    )
}
ERROR_CODES: tuple[str, ...] = tuple(ERROR_SPECS)


class InternalAiError(Exception):
    """Contract violation that must reach the caller as ProblemDetail.

    ``detail`` is a short, non-sensitive sentence: it never carries prompts,
    model output, credentials, grants or full business text.
    """

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        request_id: str = "",
        invocation_id: str = "",
        retry_after_seconds: int | None = None,
    ):
        super().__init__(f"{code}: {detail}")
        self.spec = ERROR_SPECS[code]
        self.detail = detail
        self.request_id = request_id
        self.invocation_id = invocation_id
        self.retry_after_seconds = retry_after_seconds

    @property
    def code(self) -> str:
        return self.spec.code

    @property
    def status(self) -> int:
        return self.spec.status

    def to_problem(self) -> ProblemDetail:
        return ProblemDetail(
            type=f"{ERROR_TYPE_PREFIX}{self.spec.code}",
            title=self.spec.title,
            status=self.spec.status,
            code=self.spec.code,
            detail=self.detail,
            request_id=self.request_id,
            invocation_id=self.invocation_id,
            retryable=self.spec.retryable,
        )


def problem_response(error: InternalAiError) -> JSONResponse:
    """Render a contract error and log only the code and correlation ids."""
    logger.warning(
        "[内部AI][%s] 拒绝请求：%s %s",
        error.request_id or "-",
        error.code,
        error.detail,
    )
    headers = {"Cache-Control": "no-store"}
    if error.retry_after_seconds:
        headers["Retry-After"] = str(error.retry_after_seconds)
    return JSONResponse(
        status_code=error.status,
        content=error.to_problem().model_dump(mode="json"),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )

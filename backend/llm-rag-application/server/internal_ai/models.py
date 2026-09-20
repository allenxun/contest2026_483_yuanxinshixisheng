"""Frozen wire models of the medical-platform internal AI API.

This module is the single source of truth for the delivered contract:
``docs/integration/medical-platform-ai/schemas/*.schema.json``,
``openapi.yaml`` and the examples all describe exactly these shapes, and
``tests/test_internal_ai_contract.py`` fails when they drift apart.

Everything is closed on purpose (``extra="forbid"``): an unknown field is a
contract violation, not something to ignore silently.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROTOCOL_VERSION = "1.0"

# 四个且仅四个受支持的入口用例。
USE_CASES: tuple[str, ...] = (
    "MINI_LIGHT_REPORT_EXPLANATION",
    "APP_AGENT_CONVERSATION",
    "CONSOLE_PAGE_ASSISTANT",
    "CONSOLE_PATIENT_ASSISTANT",
)
UseCase = Literal[
    "MINI_LIGHT_REPORT_EXPLANATION",
    "APP_AGENT_CONVERSATION",
    "CONSOLE_PAGE_ASSISTANT",
    "CONSOLE_PATIENT_ASSISTANT",
]

RESPONSE_STATUSES: tuple[str, ...] = ("COMPLETED", "NEEDS_CLARIFICATION", "BLOCKED")
ResponseStatus = Literal["COMPLETED", "NEEDS_CLARIFICATION", "BLOCKED"]

FINISH_REASONS: tuple[str, ...] = ("STOP", "MAX_OUTPUT_CHARS")
FinishReason = Literal["STOP", "MAX_OUTPUT_CHARS"]

SAFETY_DECISIONS: tuple[str, ...] = ("ALLOW", "WARN", "BLOCK", "ESCALATE_HUMAN")
SafetyDecision = Literal["ALLOW", "WARN", "BLOCK", "ESCALATE_HUMAN"]

CITATION_TYPES: tuple[str, ...] = ("KNOWLEDGE", "BUSINESS")
CitationType = Literal["KNOWLEDGE", "BUSINESS"]

HISTORY_ROLES: tuple[str, ...] = ("user", "assistant")
HistoryRole = Literal["user", "assistant"]

# SSE 只允许四类事件，其中 completed/failed 是互斥的终态。
EVENT_ACCEPTED = "response.accepted"
EVENT_DELTA = "response.delta"
EVENT_COMPLETED = "response.completed"
EVENT_FAILED = "response.failed"
SSE_EVENT_NAMES: tuple[str, ...] = (
    EVENT_ACCEPTED,
    EVENT_DELTA,
    EVENT_COMPLETED,
    EVENT_FAILED,
)
TERMINAL_EVENT_NAMES: tuple[str, ...] = (EVENT_COMPLETED, EVENT_FAILED)

# 请求正文限制（与设计文档冻结值一致）。正文总字节上限由
# internal_ai.max_body_bytes 配置，默认 256 KiB。
MAX_INPUT_CHARS = 4000
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 8000
MAX_CONTINUATION_STATE_BYTES = 8192
MAX_KNOWLEDGE_SCOPE_REFS = 8
MAX_OUTPUT_CHARS_LIMIT = 4000
DEFAULT_MAX_OUTPUT_CHARS = 1200
MAX_CITATION_EXCERPT_CHARS = 200

# 请求/关联标识符共用的形状（Header 与正文使用同一规则）。
IDENTIFIER_PATTERN = r"^[A-Za-z0-9._:-]{8,128}$"
# 引用、卡片、动作等由服务端生成的短标识符。
REFERENCE_PATTERN = r"^[A-Za-z0-9._:-]{1,128}$"

_CLOSED = ConfigDict(extra="forbid")


class RequestInput(BaseModel):
    """The question asked by the medical-platform end user."""

    model_config = _CLOSED

    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)


class HistoryMessage(BaseModel):
    """One previous turn supplied by the caller; the AI service stores nothing."""

    model_config = _CLOSED

    role: HistoryRole
    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)


class AiRequest(BaseModel):
    """Request body of both ``/internal/v1/ai/responses`` endpoints."""

    model_config = _CLOSED

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    use_case: UseCase
    input: RequestInput
    history: list[HistoryMessage] = Field(
        default_factory=list, max_length=MAX_HISTORY_MESSAGES
    )
    knowledge_scope_refs: list[str] = Field(
        default_factory=list, max_length=MAX_KNOWLEDGE_SCOPE_REFS
    )
    continuation_state: dict[str, Any] | None = None
    max_output_chars: int = Field(
        default=DEFAULT_MAX_OUTPUT_CHARS, ge=1, le=MAX_OUTPUT_CHARS_LIMIT
    )

    @model_validator(mode="after")
    def _check_limits(self) -> "AiRequest":
        history_chars = sum(len(message.text) for message in self.history)
        if history_chars > MAX_HISTORY_CHARS:
            raise ValueError(f"history 正文合计不能超过 {MAX_HISTORY_CHARS} 字符")
        for ref in self.knowledge_scope_refs:
            if not ref:
                raise ValueError("knowledge_scope_refs 不能包含空值")
        if self.continuation_state is not None:
            state_bytes = len(
                json.dumps(self.continuation_state, ensure_ascii=False).encode("utf-8")
            )
            if state_bytes > MAX_CONTINUATION_STATE_BYTES:
                raise ValueError(
                    f"continuation_state 不能超过 {MAX_CONTINUATION_STATE_BYTES} 字节"
                )
        return self


class Answer(BaseModel):
    """User-visible answer text."""

    model_config = _CLOSED

    text: str


class Citation(BaseModel):
    """Controlled evidence reference. Never a physical knowledge base name or URL."""

    model_config = _CLOSED

    citation_id: str = Field(pattern=REFERENCE_PATTERN)
    type: CitationType
    title: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(default="", max_length=MAX_CITATION_EXCERPT_CHARS)
    source_ref: str = Field(default="", max_length=200)
    tool_call_id: str = Field(default="", max_length=128)
    snapshot_hash: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def _check_type_fields(self) -> "Citation":
        if self.type == "KNOWLEDGE" and not (self.source_ref and self.excerpt):
            raise ValueError("KNOWLEDGE 引用必须同时提供 source_ref 和 excerpt")
        if self.type == "BUSINESS" and not (self.tool_call_id and self.snapshot_hash):
            raise ValueError("BUSINESS 引用必须同时提供 tool_call_id 和 snapshot_hash")
        return self


class AiSemanticCard(BaseModel):
    """Semantic card for the medical-platform backend; never rendered directly.

    Carries no URL, HTTP method or executable business instruction.
    """

    model_config = _CLOSED

    card_id: str = Field(pattern=REFERENCE_PATTERN)
    card_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    schema_version: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)
    refs: list[str] = Field(default_factory=list, max_length=20)


class ProposedAction(BaseModel):
    """Suggestion only. The AI service never executes a business action."""

    model_config = _CLOSED

    action_id: str = Field(pattern=REFERENCE_PATTERN)
    action_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    refs: list[str] = Field(default_factory=list, max_length=20)


class SafetyResult(BaseModel):
    """Machine-readable display gate for the calling backend."""

    model_config = _CLOSED

    decision: SafetyDecision
    codes: list[str] = Field(default_factory=list, max_length=20)
    display_allowed: bool
    requires_human_handoff: bool


class Versions(BaseModel):
    """Real versions actually used for this invocation."""

    # ``model_id`` collides with pydantic's protected ``model_`` namespace.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_id: str = Field(min_length=1, max_length=200)
    embedding_model_id: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=64)
    safety_policy_version: str = Field(min_length=1, max_length=64)
    output_schema_version: str = Field(min_length=1, max_length=32)


class Usage(BaseModel):
    """Character-level usage. Token counts are not exposed by the current chain."""

    model_config = _CLOSED

    input_chars: int = Field(ge=0)
    output_chars: int = Field(ge=0)
    retrieved_documents: int = Field(ge=0)


class AiResponse(BaseModel):
    """Completed response body, also carried by the ``response.completed`` event."""

    model_config = _CLOSED

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    output_schema_version: str = Field(min_length=1, max_length=32)
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    invocation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: ResponseStatus
    answer: Answer
    citations: list[Citation] = Field(default_factory=list, max_length=20)
    cards: list[AiSemanticCard] = Field(default_factory=list, max_length=20)
    proposed_actions: list[ProposedAction] = Field(default_factory=list, max_length=20)
    continuation_state: dict[str, Any] | None = None
    safety: SafetyResult
    versions: Versions
    usage: Usage
    finish_reason: FinishReason
    replayed: bool = False


class ProblemDetail(BaseModel):
    """RFC 9457 problem details, served as ``application/problem+json``."""

    model_config = _CLOSED

    type: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    status: int = Field(ge=400, le=599)
    code: str = Field(pattern=r"^AI_[A-Z0-9_]{2,63}$")
    detail: str = Field(default="", max_length=1000)
    request_id: str = Field(default="", max_length=128)
    invocation_id: str = Field(default="", max_length=128)
    retryable: bool


class AcceptedPayload(BaseModel):
    """``response.accepted`` event data."""

    model_config = _CLOSED

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    invocation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    use_case: UseCase
    accepted_at: str = Field(min_length=1, max_length=64)


class DeltaPayload(BaseModel):
    """``response.delta`` event data: answer text increments only."""

    model_config = _CLOSED

    request_id: str = Field(pattern=IDENTIFIER_PATTERN)
    invocation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    sequence: int = Field(ge=1)
    delta: str = Field(min_length=1)


class ReadinessCheck(BaseModel):
    """One readiness probe result."""

    model_config = _CLOSED

    name: str
    ok: bool
    detail: str = ""


class ReadinessReport(BaseModel):
    """Body of ``GET /internal/health/ready``."""

    model_config = _CLOSED

    status: Literal["READY", "NOT_READY"]
    checks: list[ReadinessCheck] = Field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == "READY"




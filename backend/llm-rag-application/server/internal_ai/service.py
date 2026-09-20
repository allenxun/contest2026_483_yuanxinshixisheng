"""Orchestration and frozen-response assembly for one internal AI invocation.

The service is stateless per call: history and ``continuation_state`` come in
with the request, and nothing is written to the web chat session tables.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping, Sequence

import httpx
from openai import APIConnectionError
from sqlalchemy import text as sql_text

from rag.business.registry import business_registry
from rag.common.configuration import settings
from rag.common.utils import logger
from server.internal_ai.engine import EngineTurn, RagAnswerEngine
from server.internal_ai.errors import InternalAiError
from server.internal_ai.models import (
    EVENT_ACCEPTED,
    EVENT_COMPLETED,
    EVENT_DELTA,
    EVENT_FAILED,
    MAX_CITATION_EXCERPT_CHARS,
    MAX_CONTINUATION_STATE_BYTES,
    MAX_KNOWLEDGE_SCOPE_REFS,
    USE_CASES,
    AcceptedPayload,
    AiRequest,
    AiResponse,
    Answer,
    Citation,
    DeltaPayload,
    ReadinessCheck,
    ReadinessReport,
    SafetyResult,
    Usage,
    Versions,
)
from server.internal_ai.security import InvocationContext

FINISH_STOP = "STOP"
FINISH_MAX_OUTPUT_CHARS = "MAX_OUTPUT_CHARS"

# 上游模型/检索超时属于可重试错误（504），不是内部错误（500）。
# APITimeoutError 是 APIConnectionError 的子类，因此这里只需列出后者。
_UPSTREAM_TIMEOUT_EXCEPTIONS: tuple[type[Exception], ...] = (
    TimeoutError,
    httpx.TimeoutException,
    APIConnectionError,
)


@dataclass(frozen=True)
class InvocationPlan:
    """Everything resolved before generation starts."""

    business_type: str
    scopes: tuple[tuple[str, str], ...]
    versions: Versions


def probe_database() -> bool:
    """Real readiness check against the metadata and vector database."""
    from rag.connector.database.session import session_scope

    try:
        with session_scope() as session:
            session.execute(sql_text("SELECT 1"))
        return True
    except Exception as exc:  # 只记录异常类型，避免泄露连接串。
        logger.warning(
            "[内部AI] readiness 数据库检查失败：%s", exc.__class__.__name__
        )
        return False


def contract_error(exc: Exception, context: InvocationContext | None) -> InternalAiError:
    """Map any failure onto the frozen ``AI_*`` catalog without leaking details."""
    if isinstance(exc, InternalAiError):
        if context and not exc.request_id:
            exc.request_id = context.request_id
            exc.invocation_id = context.invocation_id
        return exc
    if isinstance(exc, _UPSTREAM_TIMEOUT_EXCEPTIONS):
        code, detail = "AI_UPSTREAM_TIMEOUT", "AI 处理超过允许的时间，请稍后重试。"
    else:
        code, detail = (
            "AI_INTERNAL_ERROR",
            "AI 服务处理失败，请稍后重试或联系 AI 服务负责人。",
        )
    logger.error(
        "[内部AI][%s] 处理失败：%s",
        context.request_id if context else "-",
        exc,
        exc_info=exc,
    )
    return InternalAiError(
        code,
        detail,
        request_id=context.request_id if context else "",
        invocation_id=context.invocation_id if context else "",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sse_event(name: str, event_id: str, data: Mapping[str, Any]) -> dict:
    """One SSE frame: ``event`` name, decimal ``id`` and JSON ``data``."""
    return {"event": name, "id": event_id, "data": json.dumps(dict(data), ensure_ascii=False)}


def _truncate(answer_text: str, limit: int) -> tuple[str, str]:
    cleaned = (answer_text or "").strip()
    if len(cleaned) <= limit:
        return cleaned, FINISH_STOP
    return cleaned[:limit], FINISH_MAX_OUTPUT_CHARS


def _citation_title(metadata: Mapping[str, Any]) -> str:
    for key in ("filename", "title"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value[:200]
    return "知识库文档"


def _citations(documents: Sequence[Any]) -> list[Citation]:
    """Controlled knowledge citations; no physical KB name, URL or full chunk."""
    citations = []
    for index, document in enumerate(documents, start=1):
        metadata = document.metadata or {}
        scope_ref = str(metadata.get("scope_ref") or "").strip()
        excerpt = " ".join(str(document.page_content or "").split())[
            :MAX_CITATION_EXCERPT_CHARS
        ]
        if not scope_ref or not excerpt:
            continue
        citations.append(
            Citation(
                citation_id=f"cit-{index}",
                type="KNOWLEDGE",
                title=_citation_title(metadata),
                excerpt=excerpt,
                source_ref=scope_ref,
            )
        )
    return citations


def _continuation_state(state: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None
    encoded = json.dumps(dict(state), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_CONTINUATION_STATE_BYTES:
        logger.warning(
            "[内部AI] continuation_state 超过 %s 字节，本次不返回",
            MAX_CONTINUATION_STATE_BYTES,
        )
        return None
    return dict(state)


def _safety_result() -> SafetyResult:
    """Machine-readable display gate.

    The frozen safety code table has not been delivered to this repository yet,
    so no rule can fire and every answer is reported as ALLOW. The backend must
    keep its own medical review flow until the code table is registered.
    """
    return SafetyResult(
        decision="ALLOW",
        codes=[],
        display_allowed=True,
        requires_human_handoff=False,
    )


class InternalAiService:
    """Execute one invocation and assemble the frozen response or SSE events."""

    def __init__(self, engine=None, database_probe=None):
        self._engine = engine if engine is not None else RagAnswerEngine()
        self._database_probe = database_probe or probe_database

    # ---------------------------------------------------------------- readiness

    def readiness(self, config) -> ReadinessReport:
        """Report whether models, database and configuration can take traffic."""
        checks = [
            self._configuration_check(config),
            self._database_check(),
            self._generation_model_check(),
        ]
        ready = all(check.ok for check in checks)
        return ReadinessReport(
            status="READY" if ready else "NOT_READY",
            checks=checks,
        )

    @staticmethod
    def _configuration_check(config) -> ReadinessCheck:
        required = (
            ("allowed_service", config.allowed_service),
            ("api_keys", config.api_keys),
            ("protocol_version", config.protocol_version),
            ("output_schema_version", config.output_schema_version),
            ("prompt_version", config.prompt_version),
            ("safety_policy_version", config.safety_policy_version),
            ("knowledge_scopes", config.knowledge_scopes),
        )
        missing = [
            f"internal_ai.{name}" for name, value in required if not str(value).strip()
        ]
        bindings = config.get_use_case_business_types()
        unmapped = [use_case for use_case in USE_CASES if use_case not in bindings]
        details = []
        if missing:
            details.append("缺少配置：" + ", ".join(missing))
        if unmapped:
            details.append("use_case 未绑定业务身份：" + ", ".join(unmapped))
        return ReadinessCheck(
            name="configuration", ok=not details, detail="；".join(details)
        )

    def _database_check(self) -> ReadinessCheck:
        ok = bool(self._database_probe())
        return ReadinessCheck(
            name="database",
            ok=ok,
            detail="" if ok else "PostgreSQL（元数据与向量库）不可用",
        )

    @staticmethod
    def _generation_model_check() -> ReadinessCheck:
        base_url = (settings.generation_llm.base_url or settings.llm.base_url).strip()
        model_name = (
            settings.generation_llm.model_name or settings.llm.model_name
        ).strip()
        ok = bool(base_url and model_name)
        return ReadinessCheck(
            name="generation_model",
            ok=ok,
            detail="" if ok else "生成模型 base_url/model_name 未配置",
        )

    # --------------------------------------------------------------- invocation

    def prepare_invocation(self, payload: AiRequest, config) -> InvocationPlan:
        """Resolve versions, business identity and knowledge scopes.

        Runs before the SSE stream is established so every rejection can still
        be answered as ``application/problem+json``.
        """
        versions = self._versions(config)
        business_type = self._business_type(payload.use_case, config)
        scopes = self._scopes(payload.knowledge_scope_refs, business_type, config)
        return InvocationPlan(
            business_type=business_type, scopes=scopes, versions=versions
        )

    @staticmethod
    def _versions(config) -> Versions:
        required = (
            ("prompt_version", config.prompt_version),
            ("safety_policy_version", config.safety_policy_version),
            ("output_schema_version", config.output_schema_version),
        )
        missing = [
            f"internal_ai.{name}" for name, value in required if not str(value).strip()
        ]
        if missing:
            raise InternalAiError(
                "AI_SERVICE_UNAVAILABLE",
                "AI 服务版本登记缺失：" + ", ".join(missing),
            )
        return Versions(
            model_id=(settings.generation_llm.model_name or settings.llm.model_name).strip(),
            embedding_model_id=(
                settings.embeddings.modelscope_model_id
                or settings.embeddings.model_name_or_path
            ).strip(),
            prompt_version=config.prompt_version.strip(),
            safety_policy_version=config.safety_policy_version.strip(),
            output_schema_version=config.output_schema_version.strip(),
        )

    @staticmethod
    def _business_type(use_case: str, config) -> str:
        business_type = config.get_use_case_business_types().get(use_case, "")
        if not business_type:
            raise InternalAiError(
                "AI_SERVICE_UNAVAILABLE",
                f"use_case {use_case} 未绑定业务身份（internal_ai.use_case_business_types）。",
            )
        try:
            business_registry.get(business_type)
        except ValueError as exc:
            raise InternalAiError(
                "AI_SERVICE_UNAVAILABLE",
                f"use_case 绑定的业务身份未登记：{business_type}",
            ) from exc
        return business_type

    @staticmethod
    def _scopes(
        refs: Sequence[str], business_type: str, config
    ) -> tuple[tuple[str, str], ...]:
        """Map registered scope refs onto knowledge bases visible to this use_case."""
        registry = config.get_knowledge_scopes()
        identity = business_registry.get(business_type)
        visible = set(
            business_registry.filter_knowledge_bases(identity, tuple(registry.values()))
        )
        if refs:
            unknown = [ref for ref in refs if ref not in registry]
            if unknown:
                raise InternalAiError(
                    "AI_REQUEST_INVALID",
                    "knowledge_scope_refs 未登记："
                    + ", ".join(unknown[:MAX_KNOWLEDGE_SCOPE_REFS]),
                )
            selected = tuple((ref, registry[ref]) for ref in dict.fromkeys(refs))
            denied = [ref for ref, kb_name in selected if kb_name not in visible]
            if denied:
                raise InternalAiError(
                    "AI_REQUEST_INVALID",
                    "knowledge_scope_refs 超出当前 use_case 可见范围：" + ", ".join(denied),
                )
            return selected
        return tuple(
            (ref, kb_name) for ref, kb_name in registry.items() if kb_name in visible
        )

    def invoke(
        self, payload: AiRequest, context: InvocationContext, plan: InvocationPlan
    ) -> AiResponse:
        """Run one blocking invocation and return the completed response."""
        history = _history(payload)
        turn = self._engine.prepare(
            text=payload.input.text,
            history=history,
            business_type=plan.business_type,
            scopes=plan.scopes,
            continuation_state=payload.continuation_state,
        )
        if turn.needs_generation:
            generated = self._engine.generate(
                turn, text=payload.input.text, history=history
            )
        else:
            generated = turn.text
        answer_text, finish_reason = _truncate(generated, payload.max_output_chars)
        return self._response(
            payload, context, plan, turn, answer_text, finish_reason
        )

    def stream(
        self, payload: AiRequest, context: InvocationContext, plan: InvocationPlan
    ) -> Iterator[dict]:
        """Yield SSE frames: accepted, deltas, then exactly one terminal event."""
        sequence = 0

        def next_id() -> str:
            nonlocal sequence
            sequence += 1
            return str(sequence)

        accepted = AcceptedPayload(
            request_id=context.request_id,
            invocation_id=context.invocation_id,
            use_case=payload.use_case,
            accepted_at=_now(),
        )
        yield _sse_event(EVENT_ACCEPTED, next_id(), accepted.model_dump(mode="json"))

        history = _history(payload)
        answer_parts: list[str] = []
        finish_reason = FINISH_STOP
        try:
            turn = self._engine.prepare(
                text=payload.input.text,
                history=history,
                business_type=plan.business_type,
                scopes=plan.scopes,
                continuation_state=payload.continuation_state,
            )
            if turn.needs_generation:
                limit = payload.max_output_chars
                for delta in self._engine.generate_stream(
                    turn, text=payload.input.text, history=history
                ):
                    if not delta:
                        continue
                    remaining = limit - sum(len(part) for part in answer_parts)
                    if remaining <= 0:
                        finish_reason = FINISH_MAX_OUTPUT_CHARS
                        break
                    piece = delta[:remaining]
                    if len(piece) < len(delta):
                        finish_reason = FINISH_MAX_OUTPUT_CHARS
                    answer_parts.append(piece)
                    event_id = next_id()
                    payload_event = DeltaPayload(
                        request_id=context.request_id,
                        invocation_id=context.invocation_id,
                        sequence=int(event_id),
                        delta=piece,
                    )
                    yield _sse_event(
                        EVENT_DELTA, event_id, payload_event.model_dump(mode="json")
                    )
                answer_text = "".join(answer_parts).strip()
            else:
                answer_text, finish_reason = _truncate(
                    turn.text, payload.max_output_chars
                )
            response = self._response(
                payload, context, plan, turn, answer_text, finish_reason
            )
            yield _sse_event(
                EVENT_COMPLETED, next_id(), response.model_dump(mode="json")
            )
        except Exception as exc:  # SSE 已建立：只能用 response.failed 结束。
            error = contract_error(exc, context)
            yield _sse_event(
                EVENT_FAILED, next_id(), error.to_problem().model_dump(mode="json")
            )

    @staticmethod
    def _response(
        payload: AiRequest,
        context: InvocationContext,
        plan: InvocationPlan,
        turn: EngineTurn,
        answer_text: str,
        finish_reason: str,
    ) -> AiResponse:
        return AiResponse(
            output_schema_version=plan.versions.output_schema_version,
            request_id=context.request_id,
            invocation_id=context.invocation_id,
            status=turn.status,
            answer=Answer(text=answer_text),
            citations=_citations(turn.documents),
            cards=[],
            proposed_actions=[],
            continuation_state=_continuation_state(turn.continuation_state),
            safety=_safety_result(),
            versions=plan.versions,
            usage=Usage(
                input_chars=len(payload.input.text)
                + sum(len(message.text) for message in payload.history),
                output_chars=len(answer_text),
                retrieved_documents=len(turn.documents),
            ),
            finish_reason=finish_reason,
            replayed=False,
        )


def _history(payload: AiRequest) -> list[tuple[str, str]]:
    return [(message.role, message.text) for message in payload.history]




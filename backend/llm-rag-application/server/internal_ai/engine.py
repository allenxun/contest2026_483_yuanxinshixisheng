"""Per-invocation reuse of the existing intent, retrieval and generation kernel.

Nothing here touches HTTP, the web chat session tables or the legacy
``/chat/knowledge_base_chat`` handler: one request in, one answer out. Heavy
connectors are imported lazily so importing this module stays cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from langchain_core.documents import Document

from rag.chains.generate import GenerateChain
from rag.chains.query_router import limit_history
from rag.chains.retrieval import RetrievalChain, merge_document_groups
from rag.common.configuration import settings
from rag.common.utils import logger
from rag.connector.utils import get_vectorstore
from rag.intent import (
    IntentPlanBuilder,
    IntentRecognizer,
    Q2QIndex,
    build_pending_context,
    load_intent_definitions,
    load_intent_examples,
)
from rag.weijing.followup import (
    extract_followup_keys,
    load_assessment_context,
    plan_with_assessment_followup,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTENT_CATALOG_PATH = PROJECT_ROOT / "conf" / "intent_catalog.yaml"
INTENT_EXAMPLES_PATH = PROJECT_ROOT / "conf" / "intent_examples.yaml"
RETRIEVAL_SCORE_THRESHOLD = 0.35
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 8000

# 冻结契约的响应状态。
STATUS_COMPLETED = "COMPLETED"
STATUS_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


@dataclass(frozen=True)
class EngineTurn:
    """Planning plus retrieval outcome of one invocation."""

    status: str
    text: str = ""
    documents: tuple[Document, ...] = ()
    grounded: bool = False
    continuation_state: dict[str, Any] = field(default_factory=dict)
    assessment_context: str = ""

    @property
    def needs_generation(self) -> bool:
        """True when the answer still has to be generated from evidence."""
        return self.status == STATUS_COMPLETED and not self.text


@lru_cache
def _intent_kit():
    """Build the intent recognizer once, on first real invocation."""
    from rag.connector.base import embedding_model, router_llm

    definitions = load_intent_definitions(INTENT_CATALOG_PATH)
    recognizer = IntentRecognizer(
        llm=router_llm,
        definitions=definitions,
        q2q_index=Q2QIndex(
            embedding_model, load_intent_examples(INTENT_EXAMPLES_PATH)
        ),
    )
    return recognizer, IntentPlanBuilder(definitions)


class RagAnswerEngine:
    """Run intent planning, hybrid retrieval and generation for one invocation."""

    def prepare(
        self,
        *,
        text: str,
        history: Sequence[tuple[str, str]],
        business_type: str,
        scopes: Sequence[tuple[str, str]],
        continuation_state: Mapping[str, Any] | None,
    ) -> EngineTurn:
        """Plan the invocation and collect evidence.

        :param scopes: registered ``(scope_ref, knowledge_base)`` pairs.
        """
        recognizer, plan_builder = _intent_kit()
        knowledge_bases = tuple(dict.fromkeys(kb_name for _, kb_name in scopes))
        incoming_state = dict(continuation_state or {})
        followup_keys = extract_followup_keys(incoming_state)
        assessment_context = load_assessment_context(incoming_state)
        pending_context = dict(incoming_state)
        if assessment_context:
            pending_context["weijing_assessment_context"] = assessment_context
        intent_result = recognizer.recognize(
            text,
            history=history,
            business_type=business_type,
            pending_context=pending_context,
        )
        # 内部接口不执行工具动作：医疗云 MCP 尚未接入，本仓本地工具不在此接口开放。
        plan = plan_builder.build(
            intent_result,
            allowed_knowledge_bases=knowledge_bases,
            allowed_tools=(),
        )
        plan = plan_with_assessment_followup(plan, text, assessment_context)
        state = dict(build_pending_context(intent_result))
        state.update(followup_keys)
        if plan.status == "clarify":
            return EngineTurn(
                status=STATUS_NEEDS_CLARIFICATION,
                text=plan.response_text or "请补充您的具体需求。",
                continuation_state=state,
                assessment_context=assessment_context,
            )
        if plan.status == "oos":
            return EngineTurn(
                status=STATUS_COMPLETED,
                text=plan.response_text or "根据当前知识库资料无法回答该问题。",
                continuation_state=state,
                assessment_context=assessment_context,
            )

        ref_by_kb: dict[str, str] = {}
        for scope_ref, kb_name in scopes:
            ref_by_kb.setdefault(kb_name, scope_ref)
        groups = []
        for action in plan.actions:
            if action.action_type != "knowledge":
                continue
            groups.append(
                self._retrieve(
                    action.target_name,
                    action.query,
                    ref_by_kb.get(action.target_name, ""),
                )
            )
        documents = merge_document_groups(groups)
        logger.info(
            "[内部AI] 意图=%s 动作=%s 召回文档=%s",
            list(intent_result.intent_ids),
            len(plan.actions),
            len(documents),
        )
        return EngineTurn(
            status=STATUS_COMPLETED,
            documents=tuple(documents),
            grounded=bool(documents),
            continuation_state=state,
            assessment_context=assessment_context,
        )

    def _retrieve(self, kb_name: str, query: str, scope_ref: str) -> list[Document]:
        from rag.connector.base import embedding_model
        from rag.module.base import reranker

        vector_store = get_vectorstore(
            kb_name, settings.vector_store.type, embedding_model
        )
        chain = RetrievalChain(
            vectorstore=vector_store,
            reranker=reranker,
            score_threshold=RETRIEVAL_SCORE_THRESHOLD,
            retrieval_candidate_k=settings.reranker.retrieval_candidate_k,
            reranker_candidate_k=settings.reranker.reranker_candidate_k,
            reranker_top_k=settings.reranker.reranker_top_k,
            multi_query=False,
        )
        documents = []
        for item in chain.chain(query):
            document = item["document"]
            document.metadata = dict(document.metadata or {})
            document.metadata["kb_name"] = kb_name
            # 引用只允许回传登记的 scope_ref，物理知识库名不出现在响应中。
            document.metadata["scope_ref"] = scope_ref
            documents.append(document)
        return documents

    def generate(self, turn: EngineTurn, *, text: str, history) -> str:
        """Generate the whole answer at once."""
        return "".join(self._chunks(turn, text=text, history=history, stream=False))

    def generate_stream(self, turn: EngineTurn, *, text: str, history) -> Iterator[str]:
        """Yield answer text increments."""
        yield from self._chunks(turn, text=text, history=history, stream=True)

    def _chunks(self, turn: EngineTurn, *, text: str, history, stream: bool):
        from rag.connector.base import generation_llm

        chain = GenerateChain(llm=generation_llm, stream=stream)
        return chain.chain(
            query=text,
            docs=list(turn.documents),
            history=limit_history(
                list(history),
                max_messages=MAX_HISTORY_MESSAGES,
                max_chars=MAX_HISTORY_CHARS,
            ),
            use_knowledge_base=turn.grounded,
            enable_thinking=False,
            assessment_context=turn.assessment_context,
        )


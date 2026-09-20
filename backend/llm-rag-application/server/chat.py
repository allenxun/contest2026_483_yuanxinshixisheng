import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

from fastapi import Body, Depends, Request
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from rag.business.registry import business_registry
from rag.chains.generate import GenerateChain
from rag.chains.query_router import limit_history
from rag.chains.retrieval import RetrievalChain, merge_document_groups
from rag.common.configuration import settings
from rag.common.utils import logger
from rag.connector.base import embedding_model, generation_llm, router_llm
from rag.connector.database.repository.chat_history_repository import (
    get_chat_pending_context,
    get_latest_weijing_assessment_id,
)
from rag.connector.database.repository.weijing_assessment_repository import (
    WeijingAssessmentNotFoundError,
    WeijingAssessmentRepository,
)
from rag.weijing.followup import (
    compact_weijing_assessment_context,
    plan_with_assessment_followup,
)
from rag.connector.utils import get_vectorstore
from rag.intent import (
    IntentPlanBuilder,
    IntentRecognizer,
    Q2QIndex,
    build_pending_context,
    evaluate_retrieval,
    load_intent_definitions,
    load_intent_examples,
)
from rag.module.base import reranker
from rag.tools import ToolContext, ToolExecutor, tool_registry
from server.business_identity import resolve_business_identity
from server.identity import Principal, get_current_principal
from server.knowledge import KBServiceFactory
from server.limiter import limiter


_INTENT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "conf" / "intent_catalog.yaml"
_INTENT_EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "conf" / "intent_examples.yaml"
_INTENT_DEFINITIONS = load_intent_definitions(_INTENT_CATALOG_PATH)
_Q2Q_INDEX = Q2QIndex(embedding_model, load_intent_examples(_INTENT_EXAMPLES_PATH))
_INTENT_RECOGNIZER = IntentRecognizer(
    llm=router_llm,
    definitions=_INTENT_DEFINITIONS,
    q2q_index=_Q2Q_INDEX,
)
_INTENT_PLAN_BUILDER = IntentPlanBuilder(_INTENT_DEFINITIONS)
def _get_weijing_assessment_context(session_id: str, principal: Principal) -> str:
    assessment_id = get_latest_weijing_assessment_id(session_id, principal.user_id)
    repository = WeijingAssessmentRepository()
    try:
        if assessment_id:
            assessment = repository.get(
                assessment_id,
                principal.user_id,
                principal.organization_id,
            )
        else:
            assessment = repository.latest_for_user(
                principal.user_id,
                principal.organization_id,
            )
            if assessment is None:
                return ""
    except WeijingAssessmentNotFoundError:
        return ""
    return compact_weijing_assessment_context(assessment)


def assessment_followup_can_skip_clarification(query: str, assessment_context: str) -> bool:
    from rag.weijing.followup import assessment_followup_can_skip_clarification as _can_skip

    return _can_skip(query, assessment_context)


def _plan_with_assessment_followup(plan, query: str, assessment_context: str):
    return plan_with_assessment_followup(plan, query, assessment_context)


def _safe_log_text(value: str, max_length: int = 300) -> str:
    return " ".join((value or "未提供").split())[:max_length]


def _task_summary(intent_result, plan, action_results) -> str:
    payload = {
        "intent_status": intent_result.status,
        "user_goal": intent_result.frame.normalized_user_goal,
        "underlying_goal": intent_result.frame.underlying_goal,
        "information_needs": list(intent_result.frame.information_needs),
        "intent_ids": list(intent_result.intent_ids),
        "missing_slots": list(intent_result.frame.missing_slots),
        "clarification": plan.response_text,
        "actions": [
            {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "target_name": action.target_name,
                "status": action_results.get(action.action_id, {}).get("status", "not_executed"),
            }
            for action in plan.actions
        ],
        "reason_summary": intent_result.reason_summary,
    }
    return json.dumps(payload, ensure_ascii=False)


def _document_trace(document):
    metadata = document.metadata or {}
    source_url = ""
    for key in ("source_url", "notion_url", "url"):
        candidate = str(metadata.get(key) or "").strip()
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            source_url = candidate
            break
    return {
        "knowledge_base": metadata.get("kb_name"),
        "filename": metadata.get("filename")
        or metadata.get("title")
        or metadata.get("source")
        or "未知来源",
        "chunk_index": metadata.get("chunk_index"),
        "similarity_score": metadata.get("dense_score"),
        "sparse_score": metadata.get("sparse_score"),
        "fusion_score": metadata.get("fusion_score"),
        "source_url": source_url,
        "content": document.page_content,
    }


async def _retrieve_knowledge(
    *,
    kb_name: str,
    retrieval_query: str,
    score_threshold: float,
    multi_query: bool,
):
    kb = await run_in_threadpool(KBServiceFactory.get_service_by_name, kb_name)
    if kb is None:
        return [], {}, "knowledge_base_not_found"
    vector_store = await run_in_threadpool(
        get_vectorstore,
        kb_name,
        settings.vector_store.type,
        embedding_model,
    )
    chain = RetrievalChain(
        vectorstore=vector_store,
        reranker=reranker,
        score_threshold=score_threshold,
        retrieval_candidate_k=settings.reranker.retrieval_candidate_k,
        reranker_candidate_k=settings.reranker.reranker_candidate_k,
        reranker_top_k=settings.reranker.reranker_top_k,
        multi_query=multi_query,
    )
    results = await run_in_threadpool(chain.chain, retrieval_query)
    action_documents = []
    for item in results:
        document = item["document"]
        document.metadata = dict(document.metadata or {})
        document.metadata["kb_name"] = kb_name
        document.metadata["retrieval_query"] = retrieval_query
        action_documents.append(document)
    diagnostics = {
        "query": retrieval_query,
        "generated_queries": chain.generated_queries,
        "channels": dict(chain.channel_counts),
        "timings": dict(chain.timings),
    }
    return action_documents, diagnostics, ""


@limiter.limit("20/minute")
async def knowledge_base_chat(
    request: Request,
    query: str = Body(..., description="用户输入", examples=["你好"]),
    knowledge_base_names: List[str] = Body([], description="本次请求可使用的候选知识库"),
    session_id: str = Body("", description="当前聊天会话 ID"),
    business_type: str = Body("customer", description="当前活动业务身份"),
    history: List[Tuple[str, str]] = Body([], description="历史对话"),
    score_threshold: float = Body(0.35, description="向量相似度阈值"),
    stream: bool = Body(True, description="流式输出"),
    return_docs: bool = Body(False, description="返回检索结果"),
    show_reasoning: bool = Body(False, description="返回结构化任务与执行摘要"),
    principal: Principal = Depends(get_current_principal),
):
    request_started = time.perf_counter()
    request_id = uuid.uuid4().hex[:8]

    identity = resolve_business_identity(principal, business_type)
    business_config = business_registry.get(identity.business_type)
    requested_kbs = list(dict.fromkeys(knowledge_base_names))
    if identity.business_type == "customer":
        requested_kbs = ["weijing_knowledge"]
    allowed_kbs = (
        tuple(requested_kbs or business_config.knowledge_bases)
        if principal.has_any_role({"admin"})
        else business_registry.filter_knowledge_bases(
            business_config,
            requested_kbs or list(business_config.knowledge_bases),
        )
    )
    allowed_tool_names = frozenset(business_config.tools)
    pending_context = {}
    assessment_context = ""
    if session_id:
        pending_context = await run_in_threadpool(
            get_chat_pending_context,
            session_id,
            principal.user_id,
        )
        assessment_context = await run_in_threadpool(
            _get_weijing_assessment_context, session_id, principal
        )
        if assessment_context:
            pending_context["weijing_assessment_context"] = assessment_context
    analysis_started = time.perf_counter()
    intent_result = await run_in_threadpool(
        _INTENT_RECOGNIZER.recognize,
        query,
        history=history,
        business_type=identity.business_type,
        pending_context=pending_context,
    )
    plan = _INTENT_PLAN_BUILDER.build(
        intent_result,
        allowed_knowledge_bases=allowed_kbs,
        allowed_tools=allowed_tool_names,
    )
    plan = _plan_with_assessment_followup(plan, query, assessment_context)
    analysis_seconds = time.perf_counter() - analysis_started
    logger.info(
        "[意图路由][%s] 身份=%s | 状态=%s | 意图=%s | 动作=%s | 摘要=%s",
        request_id,
        identity.business_type,
        intent_result.status,
        list(intent_result.intent_ids),
        [(action.action_id, action.action_type) for action in plan.actions],
        _safe_log_text(intent_result.reason_summary),
    )

    retrieval_diagnostics = {}
    action_results: dict[str, dict] = {}
    documents = []
    document_groups = []
    tool_results = []
    tool_executor = ToolExecutor(tool_registry)
    tool_context = ToolContext(
        user_id=principal.user_id,
        business_type=identity.business_type,
        organization_id=identity.organization_id,
    )
    if plan.status == "ready":
        for action in plan.actions:
            blocked_by = [
                dependency for dependency in action.depends_on
                if action_results.get(dependency, {}).get("status") != "success"
            ]
            if blocked_by:
                action_results[action.action_id] = {
                    "status": "blocked",
                    "error": f"依赖动作未成功：{', '.join(blocked_by)}",
                }
                continue
            if action.action_type == "chat":
                action_results[action.action_id] = {"status": "success"}
                continue
            if action.action_type == "knowledge":
                kb_name = action.target_name
                action_documents, diagnostics, retrieval_error = await _retrieve_knowledge(
                    kb_name=kb_name,
                    retrieval_query=action.query,
                    score_threshold=score_threshold,
                    multi_query=False,
                )
                if retrieval_error:
                    action_results[action.action_id] = {
                        "status": "error",
                        "error": retrieval_error,
                    }
                    continue
                document_groups.append(action_documents)
                retrieval_diagnostics[action.action_id] = diagnostics
                action_results[action.action_id] = {
                    "status": "success" if action_documents else "empty",
                    "documents": len(action_documents),
                }
                continue
            dependency_results = {
                result.task_id: result for result in tool_results
                if result.task_id in action.depends_on
            }
            result = await tool_executor.execute(
                task_id=action.action_id,
                tool_name=action.target_name,
                arguments=dict(action.arguments),
                allowed_tools=allowed_tool_names,
                context=tool_context,
                dependency_results=dependency_results,
            )
            tool_results.append(result)
            action_results[action.action_id] = {
                "status": result.status,
                "error": result.error,
            }

    documents = merge_document_groups(document_groups)
    knowledge_actions = [action for action in plan.actions if action.action_type == "knowledge"]
    retrieval_evaluation = None
    needs_retrieval_evaluation = (
        len(intent_result.frame.information_needs) > 1 or not documents
    )
    if plan.status == "ready" and knowledge_actions and needs_retrieval_evaluation:
        retrieval_evaluation = await run_in_threadpool(
            evaluate_retrieval,
            underlying_goal=(
                intent_result.frame.underlying_goal
                or intent_result.frame.normalized_user_goal
            ),
            information_needs=intent_result.frame.information_needs,
            executed_queries=[action.query for action in knowledge_actions],
            documents=documents,
            llm=router_llm,
        )
        if retrieval_evaluation.should_replan:
            retry_kb = knowledge_actions[0].target_name
            for index, revised_query in enumerate(
                retrieval_evaluation.revised_queries, start=1
            ):
                retry_id = f"replan:{index}"
                retry_documents, diagnostics, retrieval_error = await _retrieve_knowledge(
                    kb_name=retry_kb,
                    retrieval_query=revised_query,
                    score_threshold=score_threshold,
                    multi_query=False,
                )
                document_groups.append(retry_documents)
                retrieval_diagnostics[retry_id] = diagnostics
                action_results[retry_id] = {
                    "status": "error" if retrieval_error else (
                        "success" if retry_documents else "empty"
                    ),
                    "documents": len(retry_documents),
                    "error": retrieval_error,
                }
            documents = merge_document_groups(document_groups)

    generation_history = limit_history(history, max_messages=10, max_chars=8000)
    grounded_mode = plan.grounded
    task_summary = _task_summary(intent_result, plan, action_results)
    decision_trace = {"pending_context": build_pending_context(intent_result)}
    if show_reasoning or return_docs:
        decision_trace.update({
            "business_type": identity.business_type,
            "intent_status": intent_result.status,
            "user_goal": intent_result.frame.normalized_user_goal,
            "underlying_goal": intent_result.frame.underlying_goal,
            "information_needs": list(intent_result.frame.information_needs),
            "retrieval_queries": list(intent_result.frame.retrieval_queries),
            "intent_ids": list(intent_result.intent_ids),
            "candidate_intent_ids": list(intent_result.candidate_intent_ids),
            "missing_slots": list(intent_result.frame.missing_slots),
            "actions": [asdict(action) for action in plan.actions],
            "action_results": action_results,
            "reason_summary": intent_result.reason_summary,
            "allowed_knowledge_bases": list(allowed_kbs),
            "allowed_tools": sorted(allowed_tool_names),
            "retrieval": retrieval_diagnostics,
            "retrieval_evaluation": (
                asdict(retrieval_evaluation) if retrieval_evaluation else None
            ),
            "documents": [_document_trace(document) for document in documents],
            "tool_results": [asdict(result) for result in tool_results],
            "performance": {"intent_recognition": round(analysis_seconds, 3)},
        })
    _relevance_scores = [
        document.metadata.get("dense_score")
        for document in documents
        if isinstance(document.metadata.get("dense_score"), (int, float))
    ]
    if _relevance_scores:
        decision_trace["relevance_score"] = round(max(_relevance_scores), 4)
    trace_payload = {"decision_trace": decision_trace}
    if return_docs:
        trace_payload["docs"] = [_document_trace(document) for document in documents]

    generate_chain = GenerateChain(llm=generation_llm, stream=stream)

    async def iterator():
        full_answer = ""
        generation_started = time.perf_counter()
        try:
            if trace_payload:
                yield json.dumps(
                    {"type": "trace", "request_id": request_id, **trace_payload},
                    ensure_ascii=False,
                )
            if plan.status != "ready":
                full_answer = plan.response_text
                yield json.dumps({"type": "delta", "delta": full_answer}, ensure_ascii=False)
                yield json.dumps({
                    "type": "done",
                    "request_id": request_id,
                    "result": full_answer,
                    "performance": {
                        "intent_recognition": round(analysis_seconds, 3),
                        "generation_total": 0.0,
                        "request_total": round(time.perf_counter() - request_started, 3),
                    },
                }, ensure_ascii=False)
                return
            response_generator = generate_chain.chain(
                query=query,
                docs=documents,
                history=generation_history,
                use_knowledge_base=grounded_mode,
                enable_thinking=len(intent_result.intent_ids) > 1,
                tool_results=tool_results,
                business_policy=business_config.answer_policy,
                task_summary=task_summary,
                show_sources=business_config.show_sources,
                assessment_context=assessment_context,
            )
            async for delta in iterate_in_threadpool(iter(response_generator)):
                full_answer += delta
                yield json.dumps({"type": "delta", "delta": delta}, ensure_ascii=False)
            if plan.response_text:
                clarification = f"\n\n{plan.response_text}"
                full_answer += clarification
                yield json.dumps(
                    {"type": "delta", "delta": clarification},
                    ensure_ascii=False,
                )
            performance = {
                "intent_recognition": round(analysis_seconds, 3),
                "generation_total": round(time.perf_counter() - generation_started, 3),
                "request_total": round(time.perf_counter() - request_started, 3),
            }
            yield json.dumps({
                "type": "done",
                "request_id": request_id,
                "result": full_answer,
                "performance": performance,
            }, ensure_ascii=False)
        except Exception as exc:
            logger.error("[意图路由回答][%s] 执行失败：%s", request_id, exc, exc_info=exc)
            yield json.dumps({
                "type": "error",
                "code": "INTENT_ROUTE_EXECUTION_FAILED",
                "message": "请求处理失败，请稍后重试。",
                "request_id": request_id,
            }, ensure_ascii=False)

    return EventSourceResponse(iterator())

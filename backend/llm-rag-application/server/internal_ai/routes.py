"""The four routes delivered to the medical-platform backend.

Every rejection before the SSE stream is established is answered as
``application/problem+json``; the stream itself only ever emits the four frozen
event names. All handlers convert failures through the ``AI_*`` catalog so no
internal detail, credential or business text can leak into a response.

Note: this module deliberately does not use ``from __future__ import
annotations``. ``limiter.exempt`` wraps coroutine endpoints, and FastAPI would
then resolve the string annotations against the wrapper's module globals.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from rag.connector.database.repository.chat_history_repository import (
    get_chat_session,
    save_chat_message,
)
from rag.connector.database.repository.knowledge_base_repository import load_kb_from_db
from rag.connector.database.repository.weijing_assessment_repository import (
    WeijingAssessmentRepository,
)
from rag.weijing.catalog import CATALOG_PATH
from rag.weijing.followup import followup_continuation_state
from rag.weijing.report_input import (
    caller_organization_id,
    caller_session_id,
    caller_user_id,
)
from rag.weijing.report_parser import ReportParseError
from rag.weijing.service import WeijingAssessmentService
from server.internal_ai.errors import InternalAiError, problem_response
from server.internal_ai.security import (
    JSON_ACCEPT,
    STREAM_ACCEPT,
    authenticate_service,
    get_internal_ai_config,
    read_invocation_payload,
    read_json_object,
    validate_invocation_headers,
    validate_service_headers,
)
from server.internal_ai.service import InternalAiService, contract_error
from server.limiter import limiter

router = APIRouter(tags=["Internal AI"])

_SERVICE = InternalAiService()
_WEIJING_SERVICE = WeijingAssessmentService(WeijingAssessmentRepository())
WEIJING_KNOWLEDGE_BASE = "weijing_knowledge"


def get_internal_ai_service() -> InternalAiService:
    """Dependency returning the process-wide internal AI service."""
    return _SERVICE


def get_weijing_assessment_service() -> WeijingAssessmentService:
    return _WEIJING_SERVICE


@router.get("/internal/health/live", summary="存活探针：AI 服务进程仍在运行")
@limiter.exempt
async def liveness():
    """Only proves the process is alive; touches no model or database."""
    return JSONResponse({"status": "LIVE"})


@router.get("/internal/health/ready", summary="就绪探针：依赖已经可以接单")
@limiter.exempt
async def readiness(
    config=Depends(get_internal_ai_config),
    service=Depends(get_internal_ai_service),
):
    """200 when configuration, database and model settings can take traffic."""
    report = await run_in_threadpool(service.readiness, config)
    return JSONResponse(
        report.model_dump(mode="json"),
        status_code=200 if report.ready else 503,
    )


@router.post("/internal/v1/ai/responses", summary="一次性 JSON 问答")
@limiter.exempt
async def create_response(
    request: Request,
    config=Depends(get_internal_ai_config),
    service=Depends(get_internal_ai_service),
):
    """Answer one question and return the whole frozen response at once."""
    context = None
    try:
        authenticate_service(request, config)
        payload = await read_invocation_payload(request, config)
        context = validate_invocation_headers(
            request, payload, config, expect_accept=JSON_ACCEPT
        )
        plan = service.prepare_invocation(payload, config)
        response = await run_in_threadpool(service.invoke, payload, context, plan)
    except Exception as exc:
        return problem_response(contract_error(exc, context))
    return JSONResponse(response.model_dump(mode="json"), status_code=200)


@router.post("/internal/v1/ai/responses:stream", summary="SSE 流式问答")
@limiter.exempt
async def stream_response(
    request: Request,
    config=Depends(get_internal_ai_config),
    service=Depends(get_internal_ai_service),
):
    """Answer one question as ``text/event-stream``.

    ``Last-Event-ID`` is ignored: the contract has no resume or replay.
    """
    context = None
    try:
        authenticate_service(request, config)
        payload = await read_invocation_payload(request, config)
        context = validate_invocation_headers(
            request, payload, config, expect_accept=STREAM_ACCEPT
        )
        plan = service.prepare_invocation(payload, config)
    except Exception as exc:
        # SSE 建立前：仍然是 application/problem+json，不是事件流。
        return problem_response(contract_error(exc, context))
    return EventSourceResponse(service.stream(payload, context, plan))


@router.post("/internal/v1/weijing/reports/assess", summary="接收检测报告 JSON 并生成微晶方案")
@limiter.exempt
async def assess_structured_report(
    request: Request,
    config=Depends(get_internal_ai_config),
    weijing_service=Depends(get_weijing_assessment_service),
):
    """Backend posts extracted skin-test JSON; returns spoken text for the device."""
    context = None
    try:
        authenticate_service(request, config)
        context = validate_service_headers(
            request, config, expect_accept=JSON_ACCEPT
        )
        payload = await read_json_object(request, config)
        if load_kb_from_db(WEIJING_KNOWLEDGE_BASE)[0] is None or not CATALOG_PATH.exists():
            raise InternalAiError(
                "AI_SERVICE_UNAVAILABLE",
                "微晶知识库尚未就绪。",
                request_id=context.request_id,
                invocation_id=context.invocation_id,
            )
        user_id = caller_user_id(payload)
        organization_id = caller_organization_id(payload)
        session_id = caller_session_id(payload)
        if session_id and get_chat_session(session_id, user_id) is None:
            raise InternalAiError(
                "AI_REQUEST_INVALID",
                "session_id 无效或不属于该用户。",
                request_id=context.request_id,
                invocation_id=context.invocation_id,
            )

        def _run():
            return weijing_service.assess_from_payload(
                payload,
                user_id=user_id,
                organization_id=organization_id,
            )

        assessment = await run_in_threadpool(_run)
        if session_id:
            _persist_assessment_chat(session_id, user_id, assessment)
    except FileNotFoundError:
        return problem_response(
            InternalAiError(
                "AI_SERVICE_UNAVAILABLE",
                "微晶知识库尚未就绪。",
                request_id=context.request_id if context else "",
                invocation_id=context.invocation_id if context else "",
            )
        )
    except ReportParseError as exc:
        return problem_response(
            InternalAiError(
                "AI_REQUEST_INVALID",
                str(exc),
                request_id=context.request_id if context else "",
                invocation_id=context.invocation_id if context else "",
            )
        )
    except Exception as exc:
        return problem_response(contract_error(exc, context))
    return JSONResponse(
        {
            "request_id": context.request_id,
            "invocation_id": context.invocation_id,
            "spoken_text": assessment.rendered_markdown,
            "assessment": assessment.model_dump(mode="json"),
            "continuation_state": followup_continuation_state(assessment),
        },
        status_code=200,
    )


def _persist_assessment_chat(session_id, user_id, assessment):
    user_message = save_chat_message(
        session_id=session_id,
        user_id=user_id,
        role="user",
        content="已同步检测报告",
    )
    save_chat_message(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content=assessment.rendered_markdown,
        parent_message_id=user_message["message_id"],
        decision_trace={
            "message_kind": "weijing_assessment",
            "assessment_id": assessment.assessment_id,
            "report_id": assessment.report.report_id,
            "knowledge_base": WEIJING_KNOWLEDGE_BASE,
            "knowledge_version": assessment.plan.knowledge_version,
        },
    )

from fastapi import Depends, File, Form, HTTPException, UploadFile, status

from rag.connector.database.repository.chat_history_repository import get_chat_session
from rag.connector.database.repository.knowledge_base_repository import load_kb_from_db
from rag.connector.database.repository.weijing_assessment_repository import (
    WeijingAssessmentNotFoundError,
    WeijingAssessmentRepository,
)
from rag.weijing.catalog import CATALOG_PATH
from rag.weijing.models import WeijingAssessment
from rag.weijing.report_parser import MAX_REPORT_BYTES, ReportParseError, ReportUploadError
from rag.weijing.service import WeijingAssessmentService
from server.identity import Principal, get_current_principal


WEIJING_KNOWLEDGE_BASE = "weijing_knowledge"
_SERVICE = WeijingAssessmentService(WeijingAssessmentRepository())


async def assess_report(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    principal: Principal = Depends(get_current_principal),
) -> WeijingAssessment:
    if get_chat_session(session_id, principal.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    if load_kb_from_db(WEIJING_KNOWLEDGE_BASE)[0] is None or not CATALOG_PATH.exists():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "微晶知识库尚未就绪")
    data = await file.read(MAX_REPORT_BYTES + 1)
    try:
        return _SERVICE.assess(
            data,
            file.filename or "",
            user_id=principal.user_id,
            organization_id=principal.organization_id,
        )
    except ReportUploadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ReportParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


def get_assessment(
    assessment_id: str,
    principal: Principal = Depends(get_current_principal),
) -> WeijingAssessment:
    try:
        return _SERVICE.get(
            assessment_id,
            user_id=principal.user_id,
            organization_id=principal.organization_id,
        )
    except WeijingAssessmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "评估不存在") from exc

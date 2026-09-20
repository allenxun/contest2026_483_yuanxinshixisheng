import uuid
from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import delete, desc, select

from rag.connector.database.base import SessionLocal, engine
from rag.connector.database.models.chat_history_model import (
    ChatMessageModel,
    ChatSessionModel,
)


_tables_ready = False
_tables_lock = Lock()


def _ensure_tables() -> None:
    global _tables_ready
    if _tables_ready:
        return
    with _tables_lock:
        if _tables_ready:
            return
        ChatSessionModel.__table__.create(bind=engine, checkfirst=True)
        ChatMessageModel.__table__.create(bind=engine, checkfirst=True)
        _tables_ready = True


def create_chat_session(
    user_id: str,
    knowledge_base_name: str | None = None,
    title: str = "新会话",
) -> dict:
    _ensure_tables()
    record = ChatSessionModel(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        knowledge_base_name=knowledge_base_name,
    )
    with SessionLocal.begin() as session:
        session.add(record)
        session.flush()
        result = _session_to_dict(record)
    return result


def get_chat_session(session_id: str, user_id: str) -> dict | None:
    _ensure_tables()
    with SessionLocal() as session:
        record = session.scalar(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        return _session_to_dict(record) if record else None


def list_chat_sessions(user_id: str, limit: int = 50) -> list[dict]:
    _ensure_tables()
    with SessionLocal() as session:
        records = session.scalars(
            select(ChatSessionModel)
            .where(ChatSessionModel.user_id == user_id)
            .order_by(desc(ChatSessionModel.updated_at))
            .limit(limit)
        ).all()
        return [_session_to_dict(record) for record in records]


def list_chat_messages(session_id: str, user_id: str) -> list[dict]:
    _ensure_tables()
    with SessionLocal() as session:
        owned = session.scalar(
            select(ChatSessionModel.session_id).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        if owned is None:
            return []
        records = session.scalars(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at, ChatMessageModel.message_id)
        ).all()
        return [_message_to_dict(record) for record in records]


def get_chat_pending_context(session_id: str, user_id: str) -> dict:
    """Return pending clarification state from the latest assistant message."""
    _ensure_tables()
    with SessionLocal() as session:
        owned = session.scalar(
            select(ChatSessionModel.session_id).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        if owned is None:
            return {}
        record = session.scalar(
            select(ChatMessageModel)
            .where(
                ChatMessageModel.session_id == session_id,
                ChatMessageModel.role == "assistant",
            )
            .order_by(desc(ChatMessageModel.created_at), desc(ChatMessageModel.message_id))
            .limit(1)
        )
        if record is None or not isinstance(record.decision_trace, dict):
            return {}
        pending_context = record.decision_trace.get("pending_context")
        return dict(pending_context) if isinstance(pending_context, dict) else {}


def get_latest_weijing_assessment_id(session_id: str, user_id: str) -> str | None:
    """Return the latest persisted microcrystal assessment linked to an owned chat."""
    _ensure_tables()
    with SessionLocal() as session:
        owned = session.scalar(
            select(ChatSessionModel.session_id).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        if owned is None:
            return None
        records = session.scalars(
            select(ChatMessageModel)
            .where(
                ChatMessageModel.session_id == session_id,
                ChatMessageModel.role == "assistant",
            )
            .order_by(desc(ChatMessageModel.created_at), desc(ChatMessageModel.message_id))
        ).all()
        for record in records:
            trace = record.decision_trace if isinstance(record.decision_trace, dict) else {}
            if trace.get("message_kind") == "weijing_assessment":
                assessment_id = str(trace.get("assessment_id") or "").strip()
                return assessment_id or None
        return None


def update_chat_session_knowledge_base(
    session_id: str, user_id: str, knowledge_base_name: str
) -> None:
    _ensure_tables()
    with SessionLocal.begin() as session:
        record = session.scalar(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        if record is None:
            raise ValueError("Chat session does not exist or is not owned by this user")
        record.knowledge_base_name = knowledge_base_name
        record.updated_at = datetime.utcnow()


def rename_chat_session(session_id: str, user_id: str, title: str) -> bool:
    """Rename one owned conversation without exposing cross-user records."""
    normalized_title = " ".join((title or "").split())
    if not normalized_title:
        raise ValueError("Conversation title cannot be empty")
    if len(normalized_title) > 60:
        raise ValueError("Conversation title cannot exceed 60 characters")

    _ensure_tables()
    with SessionLocal.begin() as session:
        record = session.scalar(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        if record is None:
            return False
        record.title = normalized_title
        record.updated_at = datetime.utcnow()
        return True


def delete_chat_session(session_id: str, user_id: str) -> bool:
    """Delete one owned conversation and all of its messages."""
    _ensure_tables()
    with SessionLocal.begin() as session:
        owned = session.scalar(
            select(ChatSessionModel.session_id).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        if owned is None:
            return False
        session.execute(
            delete(ChatMessageModel).where(ChatMessageModel.session_id == session_id)
        )
        session.execute(
            delete(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        return True


def save_chat_message(
    *,
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    parent_message_id: str | None = None,
    trace_id: str | None = None,
    status: str = "complete",
    source_documents: list | None = None,
    decision_trace: dict | None = None,
) -> dict:
    if role not in {"user", "assistant"}:
        raise ValueError(f"Unsupported chat role: {role}")
    _ensure_tables()
    with SessionLocal.begin() as session:
        chat_session = session.scalar(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
            ).with_for_update()
        )
        if chat_session is None:
            raise ValueError("Chat session does not exist or is not owned by this user")

        created_at = datetime.utcnow()
        latest_created_at = session.scalar(
            select(ChatMessageModel.created_at)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(desc(ChatMessageModel.created_at))
            .limit(1)
        )
        if latest_created_at is not None and created_at <= latest_created_at:
            created_at = latest_created_at + timedelta(microseconds=1)

        record = ChatMessageModel(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            parent_message_id=parent_message_id,
            trace_id=trace_id,
            status=status,
            source_documents=source_documents or [],
            decision_trace=decision_trace or {},
            created_at=created_at,
        )
        session.add(record)
        chat_session.updated_at = datetime.utcnow()
        if role == "user" and chat_session.title == "新会话":
            chat_session.title = _make_title(content)
        session.flush()
        result = _message_to_dict(record)
    return result


def _make_title(content: str, max_length: int = 30) -> str:
    normalized = " ".join((content or "").split())
    if not normalized:
        return "新会话"
    return normalized if len(normalized) <= max_length else normalized[:max_length] + "…"


def _session_to_dict(record: ChatSessionModel) -> dict:
    return {
        "session_id": record.session_id,
        "user_id": record.user_id,
        "title": record.title,
        "knowledge_base_name": record.knowledge_base_name,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _message_to_dict(record: ChatMessageModel) -> dict:
    return {
        "message_id": record.message_id,
        "session_id": record.session_id,
        "user_id": record.user_id,
        "role": record.role,
        "context": record.content,
        "parent_message_id": record.parent_message_id,
        "trace_id": record.trace_id,
        "status": record.status,
        "source_documents": record.source_documents or [],
        "decision_trace": record.decision_trace or None,
        "created_at": record.created_at,
    }

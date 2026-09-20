import uuid
from datetime import datetime
from threading import Lock

from sqlalchemy import delete, select

from rag.connector.database.base import SessionLocal, engine
from rag.connector.database.models.chat_history_model import ChatMessageModel, ChatSessionModel
from rag.connector.database.models.user_rights_model import (
    UserBusinessIdentityModel,
    UserConsentModel,
    UserFeedbackModel,
    UserPreferenceModel,
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
        UserConsentModel.__table__.create(bind=engine, checkfirst=True)
        UserFeedbackModel.__table__.create(bind=engine, checkfirst=True)
        UserPreferenceModel.__table__.create(bind=engine, checkfirst=True)
        UserBusinessIdentityModel.__table__.create(bind=engine, checkfirst=True)
        _tables_ready = True


def get_business_identity(user_id: str) -> str | None:
    _ensure_tables()
    with SessionLocal() as session:
        return session.scalar(
            select(UserBusinessIdentityModel.business_type).where(
                UserBusinessIdentityModel.user_id == user_id
            )
        )


def assign_business_identity(user_id: str, business_type: str) -> None:
    """Assign an identity once; registration must not change an existing one."""
    _ensure_tables()
    with SessionLocal.begin() as session:
        identity = session.get(UserBusinessIdentityModel, user_id)
        if identity is None:
            session.add(
                UserBusinessIdentityModel(
                    user_id=user_id,
                    business_type=business_type,
                )
            )
        elif identity.business_type != business_type:
            raise ValueError("该账号已经设置业务身份，不能通过注册流程修改。")


def personalization_enabled(user_id: str) -> bool:
    """Return the user's choice; personalization is opt-out by default."""
    _ensure_tables()
    with SessionLocal() as session:
        value = session.scalar(
            select(UserPreferenceModel.personalization_enabled).where(
                UserPreferenceModel.user_id == user_id
            )
        )
    return True if value is None else bool(value)


def set_personalization_enabled(user_id: str, enabled: bool) -> None:
    _ensure_tables()
    with SessionLocal.begin() as session:
        preference = session.get(UserPreferenceModel, user_id)
        if preference is None:
            session.add(
                UserPreferenceModel(
                    user_id=user_id,
                    personalization_enabled=bool(enabled),
                )
            )
        else:
            preference.personalization_enabled = bool(enabled)
            preference.updated_at = datetime.utcnow()


def has_current_consent(user_id: str, agreement_version: str) -> bool:
    _ensure_tables()
    with SessionLocal() as session:
        return session.scalar(select(UserConsentModel.consent_id).where(
            UserConsentModel.user_id == user_id,
            UserConsentModel.agreement_version == agreement_version,
            UserConsentModel.service_agreement_accepted.is_(True),
            UserConsentModel.privacy_policy_accepted.is_(True),
        )) is not None


def record_consent(user_id: str, agreement_version: str) -> None:
    _ensure_tables()
    with SessionLocal.begin() as session:
        record = session.scalar(select(UserConsentModel).where(
            UserConsentModel.user_id == user_id,
            UserConsentModel.agreement_version == agreement_version,
        ))
        if record is None:
            session.add(UserConsentModel(user_id=user_id, agreement_version=agreement_version,
                                         service_agreement_accepted=True,
                                         privacy_policy_accepted=True))
        else:
            record.service_agreement_accepted = True
            record.privacy_policy_accepted = True
            record.accepted_at = datetime.utcnow()


def create_feedback(user_id: str, category: str, content: str,
                    contact: str | None = None,
                    related_session_id: str | None = None) -> str:
    _ensure_tables()
    feedback_id = str(uuid.uuid4())
    with SessionLocal.begin() as session:
        session.add(UserFeedbackModel(
            feedback_id=feedback_id, user_id=user_id, category=category,
            content=content.strip(), contact=(contact or "").strip() or None,
            related_session_id=related_session_id,
        ))
    return feedback_id


def delete_user_personal_data(user_id: str) -> None:
    """Delete chats and consent; feedback follows the complaint retention policy."""
    _ensure_tables()
    with SessionLocal.begin() as session:
        session.execute(delete(ChatMessageModel).where(ChatMessageModel.user_id == user_id))
        session.execute(delete(ChatSessionModel).where(ChatSessionModel.user_id == user_id))
        session.execute(delete(UserConsentModel).where(UserConsentModel.user_id == user_id))
        session.execute(delete(UserPreferenceModel).where(UserPreferenceModel.user_id == user_id))

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text, UniqueConstraint

from rag.connector.database.base import Base


class UserConsentModel(Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "agreement_version", name="uq_user_consent_version"),
    )

    consent_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    agreement_version = Column(String(50), nullable=False)
    service_agreement_accepted = Column(Boolean, nullable=False, default=False)
    privacy_policy_accepted = Column(Boolean, nullable=False, default=False)
    accepted_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserFeedbackModel(Base):
    __tablename__ = "user_feedback"

    feedback_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    contact = Column(String(255), nullable=True)
    related_session_id = Column(String(36), nullable=True)
    status = Column(String(30), nullable=False, default="submitted")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserPreferenceModel(Base):
    """User-controlled product preferences that must survive new sessions."""

    __tablename__ = "user_preferences"

    user_id = Column(String(255), primary_key=True)
    personalization_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class UserBusinessIdentityModel(Base):
    """The single business identity selected when an account is registered."""

    __tablename__ = "user_business_identities"

    user_id = Column(String(255), primary_key=True)
    business_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

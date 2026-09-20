from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, Text, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from rag.connector.database.base import Base


class WeijingAssessmentModel(Base):
    __tablename__ = "weijing_assessment"
    __table_args__ = (
        UniqueConstraint("assessment_id", "revision", name="uq_weijing_assessment_revision"),
        Index("ix_weijing_assessment_owner", "user_id", "organization_id"),
    )

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    report_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    report: Mapped[dict] = mapped_column(JSON, nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    rendered_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

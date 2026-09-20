from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rag.connector.database.base import Base


class IndexingDiagnosticModel(Base):
    """Latest indexing observability snapshot for one knowledge-base file."""

    __tablename__ = "indexing_diagnostic"
    __table_args__ = (
        UniqueConstraint("kb_name", "file_name", name="uq_indexing_diagnostic_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    loader_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    splitter_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

from pgvector import SparseVector
from pgvector.sqlalchemy import SPARSEVEC, VECTOR
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rag.common.configuration import settings
from rag.connector.database.base import Base


class VectorDocumentModel(Base):
    """A document chunk and its embedding stored in PostgreSQL/pgvector."""

    __tablename__ = "rag_vector_document"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kb_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR(settings.embeddings.dimensions), nullable=False
    )
    sparse_embedding: Mapped[SparseVector] = mapped_column(
        SPARSEVEC(settings.embeddings.sparse_dimensions), nullable=False
    )


Index(
    "ix_rag_vector_document_embedding_hnsw",
    VectorDocumentModel.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"embedding": "vector_cosine_ops"},
)

VECTOR_DOCUMENT_SPARSE_INDEX = Index(
    "ix_rag_vector_document_sparse_hnsw",
    VectorDocumentModel.sparse_embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"sparse_embedding": "sparsevec_ip_ops"},
)

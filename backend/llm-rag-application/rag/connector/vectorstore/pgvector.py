from __future__ import annotations

import hashlib
import threading
import time
import uuid
from typing import List

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pgvector import SparseVector
from sqlalchemy import Integer, delete, func, literal, or_, select, text as sql_text

from rag.common.configuration import settings
from rag.common.document_passage import format_document_passage
from rag.connector.database.base import Base, SessionLocal, engine
from rag.connector.database.models.vector_document_model import (
    VECTOR_DOCUMENT_SPARSE_INDEX,
    VectorDocumentModel,
)
from rag.connector.database.utils import KnowledgeFile
from rag.connector.vectorstore.base import VectorStoreBase


def md5_encryption(data: str) -> str:
    return hashlib.md5(data.encode("utf-8")).hexdigest()


SEARCHABLE_CHUNK_TYPES = ("standalone", "child", "text summary", "table summary")
CLINICAL_METADATA_FILTER_KEYS = frozenset({
    "artifact_domain",
    "artifact_type",
    "disease_id",
    "artifact_version",
    "rule_version",
    "approval_status",
    "section_id",
})


def _metadata_conditions(filters: dict | None):
    conditions = []
    for key, value in (filters or {}).items():
        if key not in CLINICAL_METADATA_FILTER_KEYS:
            raise ValueError(f"unsupported metadata filter: {key}")
        field = VectorDocumentModel.meta_data[key].astext
        if isinstance(value, (list, tuple, set, frozenset)):
            values = [str(item) for item in value]
            if not values:
                conditions.append(literal(False))
            else:
                conditions.append(field.in_(values))
        else:
            conditions.append(field == str(value))
    return conditions


class PgVectorStore(VectorStoreBase):
    """PostgreSQL/pgvector implementation shared by all knowledge bases."""

    def __init__(self, embedding_model: Embeddings, collection_name: str):
        self.embeddings = embedding_model
        self.knowledge_base_name = collection_name
        self._timing_state = threading.local()

    @property
    def last_search_timings(self):
        return getattr(self._timing_state, "last_search_timings", {})

    def create_vectorstore(self):
        with engine.begin() as connection:
            connection.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        VectorDocumentModel.__table__.create(bind=engine, checkfirst=True)
        VECTOR_DOCUMENT_SPARSE_INDEX.create(bind=engine, checkfirst=True)

    def drop_vectorstore(self):
        self.clear_vectorstore()

    def clear_vectorstore(self):
        with SessionLocal.begin() as session:
            session.execute(
                delete(VectorDocumentModel).where(
                    VectorDocumentModel.kb_name == self.knowledge_base_name
                )
            )

    def delete_doc(self, filename: str):
        source = md5_encryption(filename)
        with SessionLocal.begin() as session:
            session.execute(
                delete(VectorDocumentModel).where(
                    VectorDocumentModel.kb_name == self.knowledge_base_name,
                    VectorDocumentModel.source == source,
                )
            )

    def update_doc(self, file: KnowledgeFile, docs: List[Document]):
        self.delete_doc(file.filename)
        return self.add_doc(file, docs)

    def add_doc(self, file: KnowledgeFile, docs: List[Document], **kwargs):
        if not docs:
            return []

        fallback_title = file.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        searchable_docs = [
            document
            for document in docs
            if document.metadata.get("multi_vector_type") in (
                None,
                *SEARCHABLE_CHUNK_TYPES,
            )
        ]
        embedding_texts = []
        for document in searchable_docs:
            if not document.metadata.get("document_title"):
                document.metadata["document_title"] = fallback_title
            embedding_texts.append(format_document_passage(document))

        dense_embeddings, sparse_embeddings = (
            self.embeddings.embed_documents_with_sparse(embedding_texts)
        )
        dense_embeddings = iter(dense_embeddings)
        sparse_embeddings = iter(sparse_embeddings)
        source = md5_encryption(file.filename)
        doc_infos = []

        with SessionLocal.begin() as session:
            for document in docs:
                metadata = {key: str(value) for key, value in document.metadata.items()}
                doc_id = metadata.get("id") or str(uuid.uuid4())
                metadata["id"] = doc_id
                metadata["source"] = source
                metadata["filename"] = file.filename
                if metadata.get("multi_vector_type") == "parent":
                    # Parent chunks are context storage only. A zero vector keeps
                    # the existing non-null schema without running an embedding.
                    embedding = [0.0] * settings.embeddings.dimensions
                    sparse_embedding = SparseVector(
                        {}, settings.embeddings.sparse_dimensions
                    )
                else:
                    embedding = next(dense_embeddings)
                    sparse_embedding = SparseVector(
                        next(sparse_embeddings),
                        settings.embeddings.sparse_dimensions,
                    )
                session.add(
                    VectorDocumentModel(
                        id=doc_id,
                        kb_name=self.knowledge_base_name,
                        source=source,
                        content=document.page_content,
                        meta_data=metadata,
                        embedding=embedding,
                        sparse_embedding=sparse_embedding,
                    )
                )
                doc_infos.append({"id": doc_id, "metadata": metadata})

        return doc_infos

    def _search_conditions(self, **kwargs):
        conditions = [VectorDocumentModel.kb_name == self.knowledge_base_name]
        conditions.extend(_metadata_conditions(kwargs.get("metadata_filters")))
        chunk_type = VectorDocumentModel.meta_data["multi_vector_type"].astext
        conditions.append(
            or_(
                chunk_type.is_(None),  # Backward compatibility for old indexes.
                chunk_type.in_(SEARCHABLE_CHUNK_TYPES),
            )
        )
        filenames = kwargs.get("filenames") or []
        if filenames:
            # The indexed source column stores md5(filename), so this filter is
            # both exact and able to use the existing database index.
            conditions.append(
                VectorDocumentModel.source.in_(
                    [md5_encryption(filename) for filename in filenames]
                )
            )
        return conditions

    def _search_dense(self, query_embedding, top_k: int, threshold, **kwargs):
        distance = VectorDocumentModel.embedding.cosine_distance(query_embedding)
        statement = (
            select(VectorDocumentModel, distance.label("distance"))
            .where(*self._search_conditions(**kwargs))
            .order_by(distance)
            .limit(top_k)
        )
        with SessionLocal() as session:
            rows = session.execute(statement).all()
            docs = [
                (
                    Document(page_content=row.content, metadata=dict(row.meta_data)),
                    1.0 - float(vector_distance),
                )
                for row, vector_distance in rows
            ]
        return self._score_threshold_process(docs, threshold, top_k)

    def _search_sparse(self, query_weights, top_k: int, **kwargs):
        query_sparse = SparseVector(
            query_weights, settings.embeddings.sparse_dimensions
        )
        negative_inner_product = VectorDocumentModel.sparse_embedding.max_inner_product(
            query_sparse
        )
        statement = (
            select(
                VectorDocumentModel,
                negative_inner_product.label("negative_inner_product"),
            )
            .where(*self._search_conditions(**kwargs))
            .order_by(negative_inner_product)
            .limit(top_k)
        )
        with SessionLocal() as session:
            rows = session.execute(statement).all()
            results = []
            for row, negative_score in rows:
                metadata = dict(row.meta_data)
                sparse_score = -float(negative_score)
                if sparse_score <= 0.0:
                    continue
                metadata["sparse_score"] = sparse_score
                results.append(
                    (Document(page_content=row.content, metadata=metadata), sparse_score)
                )
        return results

    def search_docs(self, text: str, top_k: int, threshold, **kwargs):
        search_started = time.perf_counter()
        embedding_started = time.perf_counter()
        query_embedding = self.embeddings.embed_query(text)
        embedding_seconds = time.perf_counter() - embedding_started
        database_started = time.perf_counter()
        filtered_docs = self._search_dense(query_embedding, top_k, threshold, **kwargs)

        database_seconds = time.perf_counter() - database_started
        self._timing_state.last_search_timings = {
            "query_embedding": embedding_seconds,
            "vector_database": database_seconds,
            "vector_search_total": time.perf_counter() - search_started,
        }
        return filtered_docs

    def search_hybrid_docs(
        self,
        text: str,
        dense_top_k: int,
        sparse_top_k: int,
        threshold,
        **kwargs,
    ):
        search_started = time.perf_counter()
        embedding_started = time.perf_counter()
        query_embedding, query_weights = self.embeddings.embed_query_with_sparse(text)
        embedding_seconds = time.perf_counter() - embedding_started

        dense_started = time.perf_counter()
        dense_docs = self._search_dense(
            query_embedding, dense_top_k, threshold, **kwargs
        )
        dense_seconds = time.perf_counter() - dense_started

        sparse_started = time.perf_counter()
        sparse_docs = self._search_sparse(query_weights, sparse_top_k, **kwargs)
        sparse_seconds = time.perf_counter() - sparse_started

        total_seconds = time.perf_counter() - search_started
        self._timing_state.last_search_timings = {
            "query_embedding": embedding_seconds,
            "vector_database": dense_seconds,
            "sparse_database": sparse_seconds,
            "vector_search_total": total_seconds,
        }
        return dense_docs, sparse_docs

    def list_docs_by_metadata(
        self,
        metadata_filters: dict,
        *,
        limit: int = 200,
    ) -> list[Document]:
        if not metadata_filters:
            raise ValueError("metadata filters are required")
        chunk_type = VectorDocumentModel.meta_data["multi_vector_type"].astext
        statement = (
            select(VectorDocumentModel)
            .where(
                VectorDocumentModel.kb_name == self.knowledge_base_name,
                or_(chunk_type.is_(None), chunk_type.in_(("standalone", "parent"))),
                *_metadata_conditions(metadata_filters),
            )
            .order_by(
                func.coalesce(
                    VectorDocumentModel.meta_data["chunk_index"].astext,
                    "0",
                ).cast(Integer),
                VectorDocumentModel.id,
            )
            .limit(limit)
        )
        with SessionLocal() as session:
            rows = session.scalars(statement).all()
        return [
            Document(page_content=row.content, metadata=dict(row.meta_data))
            for row in rows
        ]

    def get_documents_by_ids(self, document_ids) -> dict[str, Document]:
        document_ids = {str(document_id) for document_id in document_ids if document_id}
        if not document_ids:
            return {}
        with SessionLocal() as session:
            rows = session.scalars(
                select(VectorDocumentModel).where(
                    VectorDocumentModel.kb_name == self.knowledge_base_name,
                    VectorDocumentModel.id.in_(document_ids),
                )
            ).all()
        return {
            row.id: Document(
                page_content=row.content,
                metadata=dict(row.meta_data),
            )
            for row in rows
        }

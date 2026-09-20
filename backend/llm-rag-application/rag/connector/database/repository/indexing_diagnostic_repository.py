import hashlib

from sqlalchemy import delete, select

from rag.connector.database.base import SessionLocal, engine
from rag.connector.database.models.indexing_diagnostic_model import IndexingDiagnosticModel
from rag.connector.database.models.vector_document_model import VectorDocumentModel


def _ensure_table():
    IndexingDiagnosticModel.__table__.create(bind=engine, checkfirst=True)


def save_indexing_diagnostic(kb_name: str, file_name: str, diagnostic: dict):
    _ensure_table()
    with SessionLocal.begin() as session:
        record = session.scalar(
            select(IndexingDiagnosticModel).where(
                IndexingDiagnosticModel.kb_name == kb_name,
                IndexingDiagnosticModel.file_name == file_name,
            )
        )
        if record is None:
            record = IndexingDiagnosticModel(kb_name=kb_name, file_name=file_name)
            session.add(record)
        record.status = diagnostic.get("status", "success")
        record.loader_name = diagnostic.get("loader_name", "")
        record.splitter_name = diagnostic.get("splitter_name", "")
        record.parameters = diagnostic.get("parameters", {})
        record.metrics = diagnostic.get("metrics", {})
        record.warnings = diagnostic.get("warnings", [])
        record.error = diagnostic.get("error", "")


def get_indexing_diagnostic(kb_name: str, file_name: str) -> dict:
    _ensure_table()
    with SessionLocal() as session:
        record = session.scalar(
            select(IndexingDiagnosticModel).where(
                IndexingDiagnosticModel.kb_name == kb_name,
                IndexingDiagnosticModel.file_name == file_name,
            )
        )
        if record is None:
            return {}
        return {
            "status": record.status,
            "loader_name": record.loader_name,
            "splitter_name": record.splitter_name,
            "parameters": record.parameters,
            "metrics": record.metrics,
            "warnings": record.warnings,
            "error": record.error,
            "updated_at": record.updated_at,
        }


def list_stored_chunks(kb_name: str, file_name: str) -> list[dict]:
    """Return the chunks that were actually embedded and persisted."""
    source = hashlib.md5(file_name.encode("utf-8")).hexdigest()
    with SessionLocal() as session:
        rows = session.scalars(
            select(VectorDocumentModel).where(
                VectorDocumentModel.kb_name == kb_name,
                VectorDocumentModel.source == source,
            )
        ).all()
    chunks = [
        {
            "id": row.id,
            "content": row.content,
            "characters": len(row.content),
            "metadata": dict(row.meta_data),
            "type": row.meta_data.get("multi_vector_type", "base"),
        }
        for row in rows
    ]
    return sorted(
        chunks,
        key=lambda item: (
            item["metadata"].get("chunk_index") is None,
            int(item["metadata"].get("chunk_index", 0)),
            item["id"],
        ),
    )


def find_notion_filename(kb_name: str, page_id: str) -> str | None:
    """Find the currently indexed filename for a stable Notion page ID."""
    with SessionLocal() as session:
        metadata = session.scalar(
            select(VectorDocumentModel.meta_data).where(
                VectorDocumentModel.kb_name == kb_name,
                VectorDocumentModel.meta_data["notion_page_id"].astext == page_id,
            ).limit(1)
        )
    return metadata.get("filename") if metadata else None


def delete_indexing_diagnostics(kb_name: str, file_name: str | None = None):
    _ensure_table()
    with SessionLocal.begin() as session:
        statement = delete(IndexingDiagnosticModel).where(
            IndexingDiagnosticModel.kb_name == kb_name
        )
        if file_name is not None:
            statement = statement.where(IndexingDiagnosticModel.file_name == file_name)
        session.execute(statement)

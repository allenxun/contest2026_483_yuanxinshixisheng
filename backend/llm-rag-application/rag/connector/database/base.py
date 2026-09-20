import json
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

from rag.common.configuration import settings


KB_ROOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "local_knowledge_base",
)
os.makedirs(KB_ROOT_PATH, exist_ok=True)

database_config = settings.database
SQLALCHEMY_DATABASE_URI = URL.create(
    drivername="postgresql+psycopg",
    username=database_config.user,
    password=database_config.password,
    host=database_config.host,
    port=database_config.port,
    database=database_config.database,
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URI,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def create_tables():
    # Register every model before create_all() and enable pgvector first.
    from rag.connector.database.models import knowledge_base_model  # noqa: F401
    from rag.connector.database.models import knowledge_file_model  # noqa: F401
    from rag.connector.database.models import vector_document_model
    from rag.connector.database.models import indexing_diagnostic_model  # noqa: F401
    from rag.connector.database.models import chat_history_model  # noqa: F401
    from rag.connector.database.models import user_rights_model  # noqa: F401
    from rag.connector.database.models import product_model  # noqa: F401
    from rag.connector.database.models import weijing_assessment_model  # noqa: F401

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(bind=engine)
    # create_all() does not add columns or indexes introduced after the table existed.
    _ensure_sparse_embedding_column()
    vector_document_model.VECTOR_DOCUMENT_SPARSE_INDEX.create(
        bind=engine, checkfirst=True
    )


def _ensure_sparse_embedding_column():
    inspector = inspect(engine)
    if not inspector.has_table("rag_vector_document"):
        return
    columns = {column["name"] for column in inspector.get_columns("rag_vector_document")}
    if "sparse_embedding" in columns:
        return

    dim = settings.embeddings.sparse_dimensions
    with engine.begin() as connection:
        connection.execute(
            text(
                f"ALTER TABLE rag_vector_document "
                f"ADD COLUMN sparse_embedding sparsevec({dim})"
            )
        )
        connection.execute(
            text(
                f"UPDATE rag_vector_document "
                f"SET sparse_embedding = '{{}}/{dim}'::sparsevec "
                f"WHERE sparse_embedding IS NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE rag_vector_document "
                "ALTER COLUMN sparse_embedding SET NOT NULL"
            )
        )

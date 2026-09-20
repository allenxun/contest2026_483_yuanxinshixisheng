from functools import lru_cache

from rag.common.utils import logger
from rag.connector.vectorstore.base import VectorStoreBase
from rag.connector.vectorstore.pgvector import PgVectorStore
from rag.connector.embedding.local_embedding import LocalEmbeddings
from rag.connector.llm.openai_compatible_llm import OpenaiCompatibleLLM
from langchain_core.embeddings import Embeddings


@lru_cache
def get_embedding_model(model_name_or_path, model_engine, modelscope_model_id="") -> Embeddings:
    """Create the embedding model."""

    if model_engine in ["huggingface"]:
        return LocalEmbeddings(model_name_or_path, model_engine, modelscope_model_id)
    elif model_engine in ["openai"]:
        pass
    else:
        raise RuntimeError("Unable to find any supported embedding model. Supported engine is huggingface.")


# embedding_model = get_embedding_model(settings.embeddings.model_name_or_path,
#                                       settings.embeddings.model_engine)


@lru_cache
def get_vectorstore(knowledge_base_name,
                    vs_type,
                    embed_model) -> VectorStoreBase:
    """Get the vectorstore"""

    logger.info(f"Using {vs_type} as db to create vectorstore")
    if vs_type == "pgvector":
        vectorstore = PgVectorStore(
            embedding_model=embed_model,
            collection_name=knowledge_base_name,
        )
    else:
        raise ValueError(f"{vs_type} vector database is not supported")
    logger.info("Vector store created")
    return vectorstore


@lru_cache
def get_llm(api_key, model_name, base_url, enable_thinking=False):
    try:
        model = OpenaiCompatibleLLM(model_name=model_name,
                                    api_key=api_key,
                                    base_url=base_url,
                                    enable_thinking=enable_thinking)
        return model
    except Exception as e:
        logger.error(e)
        raise RuntimeError(f"Please check your llm cfg and make sure the api service is available !")

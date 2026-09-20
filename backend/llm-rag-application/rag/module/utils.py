from functools import lru_cache
import importlib
from rag.common.utils import logger

from rag.module.post_retrieval.reranker import Reranker


@lru_cache()
def get_reranker(model_name_or_path: str,
                 reranker_type: str,
                 modelscope_model_id: str = ""):

    logger.info(f"Loading {model_name_or_path} as model reranker")
    if reranker_type == "rank":
        reranker = Reranker(model_name_or_path, modelscope_model_id)

    return reranker


from langchain_community.document_loaders import UnstructuredFileLoader


def get_loader(name):
    try:
        project_loaders = importlib.import_module("rag.module.indexing.loader")
        if name and hasattr(project_loaders, name):
            return getattr(project_loaders, name)
        community_loaders = importlib.import_module("langchain_community.document_loaders")
        return getattr(community_loaders, name)
    except (AttributeError, ImportError, TypeError):
        return UnstructuredFileLoader

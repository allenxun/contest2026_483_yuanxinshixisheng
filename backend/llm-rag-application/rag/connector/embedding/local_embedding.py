from typing import List

import torch
from FlagEmbedding import BGEM3FlagModel
from langchain_core.embeddings import Embeddings

from rag.common.modelscope import ensure_model_available
from rag.common.utils import logger


class LocalEmbeddings(Embeddings):

    def __init__(self,
                 model_name_or_path: str,
                 model_engine: str = "huggingface",
                 modelscope_model_id: str = ""):
        self.model_name_or_path = ensure_model_available(
            model_name_or_path, modelscope_model_id
        )
        self.model_engine = model_engine
        self._init_embedding_model()

    def _init_embedding_model(self):
        if self.model_engine != "huggingface":
            raise ValueError("BGE-M3 embeddings require the huggingface engine")
        if "bge-m3" not in self.model_name_or_path.lower():
            raise ValueError("LocalEmbeddings only supports BGE-M3")

        logger.info("Loading BGE-M3 dense and sparse embeddings")
        self.embeddings = BGEM3FlagModel(
            self.model_name_or_path,
            use_fp16=torch.cuda.is_available(),
        )

    def _encode(self, texts: List[str], *, return_sparse: bool):
        output = self.embeddings.encode(
            texts,
            return_dense=True,
            return_sparse=return_sparse,
            return_colbert_vecs=False,
        )
        dense_vectors = output["dense_vecs"]
        if hasattr(dense_vectors, "tolist"):
            dense_vectors = dense_vectors.tolist()
        dense_vectors = [list(map(float, vector)) for vector in dense_vectors]

        if not return_sparse:
            return dense_vectors
        sparse_vectors = [
            {int(token_id): float(weight) for token_id, weight in weights.items()}
            for weights in output["lexical_weights"]
        ]
        return dense_vectors, sparse_vectors

    def embed_documents(self, docs: List[str]):
        return self._encode(docs, return_sparse=False)

    def embed_query(self, query: str):
        return self.embed_documents([query])[0]

    def embed_documents_with_sparse(self, docs: List[str]):
        return self._encode(docs, return_sparse=True)

    def embed_query_with_sparse(self, query: str):
        dense_vectors, sparse_vectors = self.embed_documents_with_sparse([query])
        return dense_vectors[0], sparse_vectors[0]

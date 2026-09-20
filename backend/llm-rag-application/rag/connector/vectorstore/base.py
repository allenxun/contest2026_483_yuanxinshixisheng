from abc import ABC, abstractmethod
import operator


class VectorStoreBase(ABC):
    """base class for vector store implementations"""

    @abstractmethod
    def create_vectorstore(self):
        pass

    @abstractmethod
    def drop_vectorstore(self):
        pass

    @abstractmethod
    def clear_vectorstore(self):
        pass

    @abstractmethod
    def add_doc(self, file, docs):
        pass

    @abstractmethod
    def delete_doc(self, filename):
        pass

    @abstractmethod
    def update_doc(self, file, docs):
        pass

    @abstractmethod
    def search_docs(self, text, top_k, threshold, **kwargs):
        pass

    def get_documents_by_ids(self, document_ids):
        """Return documents keyed by id when the vector store supports it."""
        return {}

    def search_hybrid_docs(
        self, text, dense_top_k, sparse_top_k, threshold, **kwargs
    ):
        """Return dense and sparse results generated from one query encoding."""
        raise NotImplementedError("hybrid retrieval is not supported")

    def list_docs_by_metadata(self, metadata_filters, *, limit=200):
        """Return stored context chunks matching an exact metadata scope."""
        raise NotImplementedError("metadata listing is not supported")

    def _score_threshold_process(self, docs, score_threshold, k):
        if score_threshold is not None:
            cmp = (
                operator.ge
            )
            docs = [
                (doc, similarity)
                for doc, similarity in docs
                if cmp(similarity, score_threshold)
            ]
        return docs[:k]



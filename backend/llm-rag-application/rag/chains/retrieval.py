
from collections import defaultdict
import time
import re
from typing import (
    Union,
    Dict,
    List,
    Optional
)

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from rag.chains.base import BaseRetrievalChain
from rag.common.utils import DocumentWithVSId, logger
from rag.connector.vectorstore.base import VectorStoreBase
# from rag.connector.knowledge_graph.base import KnowledgeGraph
from rag.module.post_retrieval.reranker import Reranker
from rag.module.pre_retrieval.multi_query import generate_queries
from rag.module.pre_retrieval.route_query import route_query_to_files
from rag.common.configuration import settings

RETRIEVAL_PREVIEW_LENGTH = 300
MAX_GENERATION_DOCUMENTS = 8


def merge_document_groups(
    groups: List[List[Document]],
    limit: int = MAX_GENERATION_DOCUMENTS,
) -> List[Document]:
    """Round-robin ranked results so each planned query keeps evidence."""
    merged = []
    seen = set()
    depth = 0
    while len(merged) < limit:
        added = False
        for group in groups:
            if depth >= len(group):
                continue
            document = group[depth]
            metadata = document.metadata or {}
            if metadata.get("kb_name") == "weijing_knowledge":
                filename = re.sub(
                    r"\s+\(\d+\)(?=\.[^.]+$)",
                    "",
                    str(metadata.get("filename") or ""),
                )
                key = (
                    "weijing_knowledge",
                    filename,
                    " ".join(document.page_content.split()),
                )
            else:
                key = (
                    metadata.get("kb_name"),
                    metadata.get("parent_id") or metadata.get("id"),
                    " ".join(document.page_content.split()),
                )
            if key in seen:
                continue
            seen.add(key)
            merged.append(document)
            added = True
            if len(merged) == limit:
                break
        if not added and all(depth >= len(group) - 1 for group in groups):
            break
        depth += 1
    return merged


def _log_retrieval_results(results: List[Dict]) -> None:
    """Log compact, readable retrieval results instead of raw Document reprs."""
    if not results:
        logger.info("[文档召回] 未找到满足条件的文档")
        return

    lines = ["", f"[文档召回] 共 {len(results)} 条", "=" * 72]
    for index, item in enumerate(results, start=1):
        document = item["document"]
        metadata = document.metadata or {}
        filename = (
            metadata.get("filename")
            or metadata.get("title")
            or metadata.get("source")
            or "未知来源"
        )
        chunk_index = metadata.get("chunk_index", "-")
        rerank_score = item.get("score")
        dense_score = metadata.get("dense_score")
        sparse_score = metadata.get("sparse_score")
        fusion_score = metadata.get("fusion_score")
        preview = " ".join(document.page_content.split())
        if len(preview) > RETRIEVAL_PREVIEW_LENGTH:
            preview = preview[:RETRIEVAL_PREVIEW_LENGTH].rstrip() + "…"

        lines.extend([
            f"[{index}] {filename}  (chunk: {chunk_index})",
            "    " + " | ".join(
                score
                for score in (
                    f"重排分数: {rerank_score:.4f}" if isinstance(rerank_score, (int, float)) else None,
                    f"Dense: {dense_score:.4f}" if isinstance(dense_score, (int, float)) else None,
                    f"Sparse: {sparse_score:.4f}" if isinstance(sparse_score, (int, float)) else None,
                    f"RRF: {fusion_score:.4f}" if isinstance(fusion_score, (int, float)) else None,
                )
                if score
            ),
            f"    内容预览: {preview}",
            "-" * 72,
        ])
    logger.info("\n".join(lines))


class RetrievalChain(BaseRetrievalChain):

    def __init__(self,
                 vectorstore: Optional[VectorStoreBase],
                 reranker: Reranker = None,
                 retrievers: List[BaseRetriever] = None,
                 top_k: int = 5,
                 score_threshold: Union[None, float] = 0.,
                 multi_query: bool = False,
                 route_query: Optional[bool] = None,
                 retrieval_candidate_k=15,
                 reranker_candidate_k=20,
                 reranker_top_k=5,
                 ):
        self.vectorstore = vectorstore
        self.reranker = reranker
        self.retrievers = retrievers
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.multi_query = multi_query
        self.route_query = (
            settings.file_routing.enabled if route_query is None else route_query
        )
        self.retrieval_candidate_k = retrieval_candidate_k
        self.reranker_candidate_k = reranker_candidate_k
        self.reranker_top_k = reranker_top_k
        self.generated_queries = []
        self.timings = {}
        self.channel_counts = {"dense": 0, "sparse": 0}

    def _reciprocal_rank(
        self, doc_lists: List[List[Document]], weights: List[float]=None, k=60
    ):
        """
        Perform weighted Reciprocal Rank Fusion on multiple rank lists.
        You can find more details about RRF here:
        https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf

        Args:
            doc_lists: A list of rank lists, where each rank list contains unique items.

        Returns:
            list: The final aggregated list of items sorted by their weighted RRF
                    scores in descending order and scores.
        """

        # Use the stable persisted document id whenever possible. Content-based
        # deduplication can incorrectly collapse equal text from different files.
        rrf_score: Dict[str, float] = defaultdict(float)
        if weights is None: weights = [1.0 for i in range(len(doc_lists))]
        documents_by_key = {}
        for doc_list, weight in zip(doc_lists, weights):
            for rank, doc in enumerate(doc_list, start=1):
                doc_key = doc.metadata.get("id") or doc.page_content
                rrf_score[doc_key] += weight / (rank + k)
                existing = documents_by_key.get(doc_key)
                if existing is None:
                    documents_by_key[doc_key] = doc
                else:
                    # Preserve channel-specific diagnostics such as dense_score
                    # and sparse_score when the same chunk appears in both lists.
                    existing.metadata.update(doc.metadata)

        sorted_docs = sorted(
            documents_by_key.values(),
            reverse=True,
            key=lambda doc: rrf_score[doc.metadata.get("id") or doc.page_content],
        )
        sorted_scores = [
            rrf_score[doc.metadata.get("id") or doc.page_content]
            for doc in sorted_docs
        ]
        return sorted_docs, sorted_scores

    def pre_retrieval(self, query: str):
        if self.multi_query:
            return generate_queries(query)
        return []

    def retrieval(self, query: str) -> Dict[str, List[Document]]:
        ensemble_docs = {}
        if self.vectorstore:
            kwargs = {}
            if self.route_query: # 根据问题筛选重点文件
                route_started = time.perf_counter()
                route_res = route_query_to_files(question=query,
                                                 knowledge_base_name=self.vectorstore.knowledge_base_name)
                self.timings["file_routing"] = self.timings.get("file_routing", 0.0) + (
                    time.perf_counter() - route_started
                )
                if route_res:
                    kwargs["filenames"] = route_res

            sparse_docs = []
            if settings.hybrid_search.enabled:
                docs, sparse_docs = self.vectorstore.search_hybrid_docs(
                    query,
                    self.retrieval_candidate_k,
                    settings.hybrid_search.candidate_k,
                    self.score_threshold,
                    **kwargs,
                )
            else:
                docs = self.vectorstore.search_docs(
                    query,
                    self.retrieval_candidate_k,
                    self.score_threshold,
                    **kwargs,
                )
            for name, seconds in getattr(self.vectorstore, "last_search_timings", {}).items():
                self.timings[name] = self.timings.get(name, 0.0) + seconds
            documents = []
            for document, score in docs:
                document.metadata["dense_score"] = score
                documents.append(
                    DocumentWithVSId(
                        **document.dict(), score=score, id=document.metadata.get("id")
                    )
                )
            ensemble_docs["vectorstore_retrieval_0"] = documents
            self.channel_counts["dense"] += len(documents)

            if sparse_docs:
                self.channel_counts["sparse"] += len(sparse_docs)
                ensemble_docs["sparse_retrieval_0"] = [
                    DocumentWithVSId(
                        **document.dict(),
                        score=score,
                        id=document.metadata.get("id"),
                    )
                    for document, score in sparse_docs
                ]

        # retrieval by using predefined retrievers
        if self.retrievers:
            for i, retriever in enumerate(self.retrievers):
                try:
                    r_docs = retriever.invoke(
                            query,
                        )
                    if len(r_docs) > 0:
                        ensemble_docs[retriever.__name__ + "_" + str(i+1)] = r_docs
                except Exception as e:
                    msg = f"使用预定义的召回器 {retriever.__name__} 检索召回文档时出错：{e}"
                    logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)

        return ensemble_docs

    def post_retrieval(self,
                       query: str,
                       docs: Dict[str, List[Document]],):
        f_documents = []
        if len(docs) == 0:
            return []

        elif len(docs) > 1:     # rank by rrf
            fusion_started = time.perf_counter()
            retrieval_names = list(docs)
            weights = [
                settings.hybrid_search.sparse_weight
                if "sparse_retrieval" in name
                else settings.hybrid_search.dense_weight
                if "vectorstore_retrieval" in name
                else 1.0
                for name in retrieval_names
            ]
            sorted_docs, sorted_scores = self._reciprocal_rank(
                [docs[name] for name in retrieval_names],
                weights=weights,
                k=settings.hybrid_search.rrf_k,
            )
            for index, document in enumerate(sorted_docs):
                metadata = dict(document.metadata)
                metadata["fusion_score"] = sorted_scores[index]
                f_documents.append(
                    DocumentWithVSId(
                        page_content=document.page_content,
                        metadata=metadata,
                        score=sorted_scores[index],
                        id=metadata.get("id"),
                    )
                )
            self.timings["rrf_fusion"] = time.perf_counter() - fusion_started

        else:
            self.timings["rrf_fusion"] = 0.0
            ids, documents = [], docs[list(docs.keys())[0]]
            for doc in documents:
                if doc.id not in ids:
                    ids.append(doc.id)
                    f_documents.append(doc)

        # rerank by pre-trained model
        if self.reranker is not None and len(f_documents) > 1:
            rerank_started = time.perf_counter()
            rerank_limit = min(len(f_documents), self.reranker_candidate_k)
            f_documents = self.reranker.rank(query, f_documents, rerank_limit)
            self.timings["reranker"] = time.perf_counter() - rerank_started
        else:
            self.timings["reranker"] = 0.0
            f_documents = [{"document": doc} for doc in f_documents]

        parent_started = time.perf_counter()
        f_documents = self._recover_parent_documents(f_documents)
        self.timings["parent_recovery"] = time.perf_counter() - parent_started
        return f_documents[:self.reranker_top_k]

    def _recover_parent_documents(self, results: List[Dict]) -> List[Dict]:
        """Replace reranked child hits with their parents, then de-duplicate."""
        parent_ids = {
            item["document"].metadata.get("parent_id")
            for item in results
            if item["document"].metadata.get("parent_id")
        }
        parent_map = self.vectorstore.get_documents_by_ids(parent_ids) if parent_ids else {}
        deduplicated = {}

        for item in results:
            child = item["document"]
            parent_id = child.metadata.get("parent_id")
            resolved = child
            result_key = child.metadata.get("id") or child.page_content

            if parent_id and parent_id in parent_map:
                parent = parent_map[parent_id]
                metadata = dict(parent.metadata)
                metadata["matched_child_id"] = child.metadata.get("id")
                metadata["matched_child_count"] = 1
                metadata["matched_child_rerank_score"] = item.get("score")
                for _score_key in ("dense_score", "sparse_score", "fusion_score"):
                    if _score_key in child.metadata:
                        metadata[_score_key] = child.metadata[_score_key]
                resolved = DocumentWithVSId(
                    page_content=parent.page_content,
                    metadata=metadata,
                    score=getattr(child, "score", 0.0),
                    id=parent_id,
                )
                result_key = parent_id

            existing = deduplicated.get(result_key)
            if existing is not None:
                existing_document = existing["document"]
                existing_document.metadata["matched_child_count"] = (
                    int(existing_document.metadata.get("matched_child_count", 1)) + 1
                )
                continue

            resolved_item = dict(item)
            resolved_item["document"] = resolved
            deduplicated[result_key] = resolved_item

        return list(deduplicated.values())

    def chain(self,
              query: str):
        chain_started = time.perf_counter()
        self.timings = {}
        self.channel_counts = {"dense": 0, "sparse": 0}
        pre_started = time.perf_counter()
        queries = self.pre_retrieval(query)
        self.generated_queries = queries
        self.timings["pre_retrieval"] = time.perf_counter() - pre_started
        docs = self.retrieval(query)
        # multi query
        for i, q in enumerate(queries):
            q_docs = self.retrieval(q)
            for r_k in q_docs: docs[str(i+1) + "_" + r_k] = q_docs[r_k]

        docs = self.post_retrieval(query, docs)
        self.timings["retrieval_total"] = time.perf_counter() - chain_started
        _log_retrieval_results(docs)
        return docs

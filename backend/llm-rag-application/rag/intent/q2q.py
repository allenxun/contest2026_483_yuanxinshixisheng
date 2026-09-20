from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from rag.intent.models import IntentExample, Q2QMatch


@dataclass(frozen=True)
class Q2QSearchResult:
    matches: tuple[Q2QMatch, ...]
    candidate_intent_ids: tuple[str, ...]

# 内存向量索引，用 embedding 模型对标注示例编码，检索时计算余弦相似度
class Q2QIndex:
    """Small in-memory Q2Q index backed by the project's embedding interface.

    It deliberately keeps storage separate from the knowledge-document index:
    Q2Q retrieves human-verified utterances and their intent labels, not answer
    passages. A persistent vector backend can implement the same ``search``
    contract later without changing the recognizer.
    """

    def __init__(self, embedding_model, examples: Sequence[IntentExample] = ()):
        self.embedding_model = embedding_model
        self._examples: list[IntentExample] = []
        self._vectors = np.empty((0, 0), dtype=np.float32)
        if examples:
            self.rebuild(examples)

    def rebuild(self, examples: Sequence[IntentExample]) -> None:
        clean = [item for item in examples if item.query and item.intent_ids]
        self._examples = clean
        if not clean:
            self._vectors = np.empty((0, 0), dtype=np.float32)
            return
        vectors = np.asarray(
            self.embedding_model.embed_documents([item.query for item in clean]),
            dtype=np.float32,
        )
        if vectors.ndim != 2 or len(vectors) != len(clean):
            raise ValueError("embedding_model returned invalid document vectors")
        self._vectors = self._normalize(vectors)

    def add(self, examples: Iterable[IntentExample]) -> None:
        self.rebuild([*self._examples, *examples])

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        min_score: float = 0.0,
        business_type: str = "",
        allowed_intent_ids: set[str] | None = None,
    ) -> Q2QSearchResult:
        if not query.strip() or not self._examples or top_k <= 0:
            return Q2QSearchResult((), ())

        query_vector = np.asarray(
            self.embedding_model.embed_query(query), dtype=np.float32
        ).reshape(1, -1)
        query_vector = self._normalize(query_vector)[0]
        if self._vectors.shape[1] != query_vector.shape[0]:
            raise ValueError("query and Q2Q example embeddings have different dimensions")

        scores = self._vectors @ query_vector
        ranked = np.argsort(-scores)
        matches: list[Q2QMatch] = []
        candidate_ids: list[str] = []
        for index in ranked:
            example = self._examples[int(index)]
            score = float(scores[int(index)])
            if score < min_score:
                continue
            if business_type and example.business_type not in {"", business_type}:
                continue
            intent_ids = tuple(
                intent_id for intent_id in example.intent_ids
                if allowed_intent_ids is None or intent_id in allowed_intent_ids
            )
            if not intent_ids:
                continue
            matches.append(Q2QMatch(
                query=example.query,
                intent_ids=intent_ids,
                score=score,
                example_id=example.example_id,
            ))
            for intent_id in intent_ids:
                if intent_id not in candidate_ids:
                    candidate_ids.append(intent_id)
            if len(matches) >= top_k:
                break
        return Q2QSearchResult(tuple(matches), tuple(candidate_ids))

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)

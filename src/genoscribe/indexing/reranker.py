from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from genoscribe.config import RERANKER_ALPHA
from genoscribe.indexing.dense_index import DenseRetriever
from genoscribe.schemas.document import Passage


class DenseReranker:
    """Semantic reranker using dense embeddings with lexical fallbacks."""

    def __init__(self, dense: DenseRetriever) -> None:
        self.dense = dense

    @staticmethod
    def _lexical_overlap(query: str, passage: Passage) -> float:
        q_tokens = {t for t in query.lower().split() if len(t) > 2}
        if not q_tokens:
            return 0.0
        p_tokens = set(passage.text.lower().split())
        overlap = len(q_tokens & p_tokens)
        return overlap / len(q_tokens)

    @staticmethod
    def _effective_noise_level(passage: Passage) -> float:
        if passage.noise_level > 0:
            return passage.noise_level
        if not passage.is_table_or_figure:
            return 0.0
        text = passage.text or ""
        if not text:
            return 0.0
        digits = sum(ch.isdigit() for ch in text)
        noise = digits / max(1, len(text))
        passage.noise_level = noise
        return noise

    def _quality_penalty(self, passage: Passage) -> float:
        noise = self._effective_noise_level(passage)
        penalty = noise * 0.7
        if passage.is_table_or_figure:
            penalty += 0.1
        return min(0.9, penalty)

    def rerank(
        self,
        passages: List[Passage],
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Tuple[Passage, float]]:
        if not passages:
            return []
        limit = top_k or len(passages)
        scores: List[tuple[float, Passage]] = []
        q_vec = self.dense.encode_query(query) if self.dense.ready() else None
        for p in passages:
            semantic = 0.0
            if q_vec is not None:
                embed = self.dense.embedding_for_passage(p)
                if embed is not None:
                    semantic = float(np.dot(q_vec, embed))
            lexical = self._lexical_overlap(query, p)
            score = RERANKER_ALPHA * semantic + (1 - RERANKER_ALPHA) * lexical
            adjusted = score * (1 - self._quality_penalty(p))
            scores.append((adjusted, p))
        scores.sort(key=lambda item: item[0], reverse=True)
        top = scores[:limit]
        return [(passage, score) for score, passage in top]


__all__ = ["DenseReranker"]

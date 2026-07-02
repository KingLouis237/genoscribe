from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np

from genoscribe.schemas.document import DocumentIndex, Passage


class LocalVectorStore:
    """In-memory cosine-similarity store backed by dense embeddings."""

    def __init__(self) -> None:
        self.passages: List[Passage] = []
        self.embeddings: np.ndarray | None = None

    @staticmethod
    def _normalize(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def build(self, passages: Sequence[Passage], embeddings: np.ndarray) -> None:
        if embeddings.ndim != 2:
            raise ValueError("Embeddings must be 2D [N, D]")
        if len(passages) != embeddings.shape[0]:
            raise ValueError("Passage/embedding count mismatch")
        self.passages = list(passages)
        self.embeddings = self._normalize(embeddings.astype(np.float32))

    def ready(self) -> bool:
        return self.embeddings is not None and len(self.passages) == (self.embeddings.shape[0] if self.embeddings is not None else 0)

    def search(self, query_vector: np.ndarray, top_k: int = 6) -> List[Tuple[Passage, float]]:
        if not self.ready():
            return []
        query = query_vector.astype(np.float32)
        denominator = np.linalg.norm(query)
        if denominator == 0:
            return []
        query = query / denominator
        sims = self.embeddings @ query
        top_idx = np.argsort(-sims)[:max(top_k, 1)]
        return [
            (self.passages[i], float(sims[i]))
            for i in top_idx
            if sims[i] > 0
        ]


__all__ = ["LocalVectorStore"]

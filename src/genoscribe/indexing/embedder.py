from __future__ import annotations

from typing import Iterable, List, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from genoscribe._config import EMBED_BATCH_SIZE


class SentenceTransformerEmbedder:
    """CPU-friendly wrapper around SentenceTransformer with optional normalization."""

    def __init__(self, model_name: str, normalize: bool = True) -> None:
        self.model_name = model_name
        self.normalize = normalize
        self._model: SentenceTransformer | None = None

    def _ensure_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def embed(self, texts: Sequence[str], batch_size: int = EMBED_BATCH_SIZE) -> np.ndarray:
        model = self._ensure_model()
        vectors = model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
            batch_size=batch_size,
        )
        return vectors.astype(np.float32)

    def embed_one(self, text: str) -> np.ndarray:
        vecs = self.embed([text])
        return vecs[0]


__all__ = ["SentenceTransformerEmbedder"]

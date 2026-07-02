from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from genoscribe.config import (
    CHUNK_MAX_SIZE,
    CHUNK_OVERLAP_PARAS,
    CHUNK_TARGET_SIZE,
    EMBED_MODEL,
    EMBED_DIM,
    QUERY_CACHE_SIZE,
)
from genoscribe.indexing.embedder import SentenceTransformerEmbedder
from genoscribe.schemas.document import DocumentIndex, Passage
from genoscribe.storage.query_cache import QueryEmbeddingCache
from genoscribe.storage.faiss_store import FAISSVectorStore

EMBED_TEXT_CHAR_LIMIT = 1600
SUMMARY_FALLBACK_THRESHOLD = 1200


class DenseRetriever:
    """SentenceTransformer-based retriever backed by persistent FAISS IndexFlatIP."""

    def __init__(
        self,
        model_name: str | None = None,
        embedder: SentenceTransformerEmbedder | None = None,
    ) -> None:
        self.model_name = model_name or EMBED_MODEL
        self.embedder = embedder or SentenceTransformerEmbedder(self.model_name, normalize=True)
        self.store = FAISSVectorStore()
        self.passage_lookup: Dict[Tuple[str, int], Passage] = {}
        self.key_to_index: Dict[Tuple[str, int], int] = {}
        self.query_cache = QueryEmbeddingCache(self.model_name, EMBED_DIM, QUERY_CACHE_SIZE)

    # ------------------------------------------------------------------ helpers
    def _manifest_payload(self) -> Dict[str, object]:
        return {
            "embedding_model": self.model_name,
            "embedding_dim": EMBED_DIM,
            "similarity": "inner_product",
            "chunker": {
                "target_size": CHUNK_TARGET_SIZE,
                "max_size": CHUNK_MAX_SIZE,
                "overlap": CHUNK_OVERLAP_PARAS,
            },
        }

    def _text_for_passage(self, passage: Passage) -> str:
        text = (passage.text or "").strip()
        if not text:
            return passage.summary or ""
        if len(text) <= EMBED_TEXT_CHAR_LIMIT:
            return text
        if passage.summary and len(text) > SUMMARY_FALLBACK_THRESHOLD:
            return passage.summary
        return text[:EMBED_TEXT_CHAR_LIMIT]

    def _collect_passages(self, documents: Sequence[DocumentIndex]) -> List[Passage]:
        passages: List[Passage] = []
        for doc in documents:
            passages.extend(doc.passages)
        return passages

    def _build_lookup(self, library: Sequence[DocumentIndex]) -> None:
        lookup: Dict[Tuple[str, int], Passage] = {}
        for doc in library:
            for passage in doc.passages:
                lookup[(passage.doc_id, passage.chunk_id)] = passage
        self.passage_lookup = lookup

    def _refresh_key_index(self) -> None:
        self.key_to_index = {key: idx for idx, key in enumerate(self.store.keys)}

    # ------------------------------------------------------------------ public
    def index(self, documents: Sequence[DocumentIndex]) -> None:
        if not documents:
            return
        passages = self._collect_passages(documents)
        if not passages:
            return
        self._build_lookup(documents)
        manifest = self._manifest_payload()
        if self.store.manifest_matches(manifest) and self.store.load():
            self._refresh_key_index()
            return
        texts = [self._text_for_passage(p) for p in passages]
        keys = [(p.doc_id, p.chunk_id) for p in passages]
        embeddings = self.embedder.embed(texts)
        self.store.build(embeddings, keys, manifest)
        self.store.load()
        self._refresh_key_index()

    def add_documents(self, documents: Sequence[DocumentIndex]) -> None:
        if not documents:
            return
        if not self.store.ready():
            self.index(documents)
            return
        passages = self._collect_passages(documents)
        if not passages:
            return
        texts = [self._text_for_passage(p) for p in passages]
        keys = [(p.doc_id, p.chunk_id) for p in passages]
        embeddings = self.embedder.embed(texts)
        self.store.append(embeddings, keys)
        self.store.load()
        self._refresh_key_index()
        for key, passage in zip(keys, passages):
            self.passage_lookup[key] = passage

    def encode_query(self, query: str, timings: Optional[Dict[str, float]] = None) -> np.ndarray | None:
        orig_query = (query or "").strip()
        if not orig_query:
            return None
        cache_key = orig_query.lower()
        start = time.perf_counter()
        cached = self.query_cache.get(cache_key)
        if cached is not None:
            if timings is not None:
                timings["dense_cache_hit"] = 1.0
                timings["dense_embed_ms"] = (time.perf_counter() - start) * 1000
            return cached
        vec = self.embedder.embed_one(orig_query)
        if timings is not None:
            timings["dense_cache_hit"] = 0.0
            timings["dense_embed_ms"] = (time.perf_counter() - start) * 1000
        self.query_cache.put(cache_key, vec)
        return vec

    def preload(self) -> None:
        """Load the embedder weights ahead of time so the first query isn't penalized."""
        try:
            self.embedder.embed_one("__genoscribe_warmup__")
        except Exception:
            # If the model isn't available yet we fall back to lazy loading.
            pass

    def search(
        self,
        query: str,
        top_k: int = 6,
        timings: Optional[Dict[str, float]] = None,
    ) -> List[tuple[Passage, float]]:
        total_start = time.perf_counter()
        query_vec = self.encode_query(query, timings)
        if query_vec is None or not self.store.ready():
            if timings is not None:
                timings.setdefault("dense_cache_hit", 0.0)
                timings.setdefault("dense_embed_ms", 0.0)
                timings["dense_search_ms"] = 0.0
                timings["dense_total_ms"] = (time.perf_counter() - total_start) * 1000
            return []
        search_start = time.perf_counter()
        hits = self.store.search(query_vec, top_k)
        if timings is not None:
            timings["dense_search_ms"] = (time.perf_counter() - search_start) * 1000
            timings["dense_total_ms"] = (time.perf_counter() - total_start) * 1000
        results: List[tuple[Passage, float]] = []
        for idx, score in hits:
            key = self.store.key_for_index(idx)
            if not key:
                continue
            passage = self.passage_lookup.get(key)
            if passage:
                results.append((passage, score))
        return results

    def ready(self) -> bool:
        return self.store.ready() and bool(self.passage_lookup)

    def embedding_for_passage(self, passage: Passage) -> np.ndarray | None:
        if not self.ready():
            return None
        key = (passage.doc_id, passage.chunk_id)
        idx = self.key_to_index.get(key)
        if idx is None:
            return None
        vec = self.store.vector_for_index(idx)
        if vec is None:
            return None
        # store already normalized
        return np.array(vec, dtype=np.float32)

    def cache_stats(self) -> Dict[str, int]:
        return self.query_cache.stats()


__all__ = ["DenseRetriever"]

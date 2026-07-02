from __future__ import annotations

import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np

from genoscribe.config import QUERY_CACHE_FILE


class QueryEmbeddingCache:
    """Persistent LRU cache for query embeddings keyed by normalized query text."""

    def __init__(
        self,
        model_name: str,
        dim: int,
        capacity: int,
        path: Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.dim = dim
        self.capacity = capacity
        self.path = path or QUERY_CACHE_FILE
        self.cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self._dirty = False
        self._load()

    # ------------------------------------------------------------------ persistence helpers
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("model") != self.model_name or payload.get("dim") != self.dim:
            return
        entries: Iterable[Tuple[str, list[float]]] = payload.get("entries", [])
        for key, vec_list in entries:
            array = np.array(vec_list, dtype=np.float32)
            if array.shape and array.shape[0] == self.dim:
                self.cache[key] = array
        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def _flush(self) -> None:
        if not self._dirty:
            return
        data = {
            "model": self.model_name,
            "dim": self.dim,
            "entries": [[key, vec.tolist()] for key, vec in self.cache.items()],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp_path, self.path)
        self._dirty = False

    # ------------------------------------------------------------------ public API
    def get(self, key: str) -> np.ndarray | None:
        vec = self.cache.get(key)
        if vec is None:
            self.misses += 1
            return None
        self.cache.move_to_end(key)
        self.hits += 1
        return vec

    def put(self, key: str, vec: np.ndarray) -> None:
        self.cache[key] = np.array(vec, dtype=np.float32)
        self.cache.move_to_end(key)
        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
        self._dirty = True
        self._flush()

    def clear(self) -> None:
        self.cache.clear()
        self._dirty = True
        if self.path.exists():
            try:
                os.remove(self.path)
            except OSError:
                pass
        self._dirty = False

    def stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "size": len(self.cache)}


__all__ = ["QueryEmbeddingCache"]

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import faiss
import numpy as np

from genoscribe.config import (
    DATA_DIR,
    VECTOR_DIR_NAME,
    VECTOR_MANIFEST_VERSION,
    INGESTION_PIPELINE_VERSION,
)


class FAISSVectorStore:
    """Persistent FAISS IndexFlatIP store with sqlite-backed key metadata."""

    def __init__(self, name: str = "passages", root: Optional[Path] = None) -> None:
        self.root = (root or (DATA_DIR / VECTOR_DIR_NAME))
        self.index_path = self.root / f"{name}.faiss"
        self.sqlite_path = self.root / f"{name}.sqlite"
        self.manifest_path = self.root / f"{name}.manifest.json"
        self.index: Optional[faiss.IndexFlatIP] = None
        self.keys: List[Tuple[str, int]] = []
        self.manifest: Dict[str, object] | None = None

    # --------------------------------------------------------------------- utils
    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _load_keys(self) -> None:
        if not self.sqlite_path.exists():
            self.keys = []
            return
        conn = self._connect()
        try:
            cur = conn.execute("SELECT doc_id, chunk_id FROM vectors ORDER BY rowid ASC")
            self.keys = [(row[0], int(row[1])) for row in cur.fetchall()]
        finally:
            conn.close()

    # ---------------------------------------------------------------- manifest
    def manifest_matches(self, expected: Dict[str, object]) -> bool:
        if not self.manifest_path.exists():
            return False
        try:
            on_disk = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        self.manifest = on_disk
        required = {
            "schema_version": VECTOR_MANIFEST_VERSION,
            "ingestion_version": INGESTION_PIPELINE_VERSION,
        }
        for key, value in required.items():
            if on_disk.get(key) != value:
                return False
        for key, value in expected.items():
            if on_disk.get(key) != value:
                return False
        return True

    def write_manifest(self, payload: Dict[str, object]) -> None:
        manifest = {
            "schema_version": VECTOR_MANIFEST_VERSION,
            "ingestion_version": INGESTION_PIPELINE_VERSION,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **payload,
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.manifest = manifest

    # -------------------------------------------------------------------- build
    def build(
        self,
        embeddings: np.ndarray,
        keys: Sequence[Tuple[str, int]],
        manifest_payload: Dict[str, object],
    ) -> None:
        if embeddings.size == 0:
            raise ValueError("Cannot build FAISS index with zero embeddings")
        self.root.mkdir(parents=True, exist_ok=True)
        # Clean previous state
        self.drop()
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
        faiss.write_index(index, str(self.index_path))
        self._write_sqlite(keys)
        self.write_manifest(manifest_payload)
        self.index = index
        self.keys = list(keys)

    def _write_sqlite(self, keys: Sequence[Tuple[str, int]]) -> None:
        conn = self._connect()
        try:
            conn.execute("CREATE TABLE vectors (doc_id TEXT, chunk_id INTEGER)")
            conn.executemany("INSERT INTO vectors (doc_id, chunk_id) VALUES (?, ?)", keys)
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------- load
    def load(self) -> bool:
        if not self.index_path.exists() or not self.sqlite_path.exists():
            return False
        self.index = faiss.read_index(str(self.index_path))
        self._load_keys()
        return True

    def ready(self) -> bool:
        return self.index is not None and bool(self.keys)

    def append(self, embeddings: np.ndarray, keys: Sequence[Tuple[str, int]]) -> None:
        if embeddings.size == 0 or not keys:
            return
        if self.index is None:
            raise RuntimeError("FAISS index not loaded; call load() before append.")
        self.index.add(embeddings)
        faiss.write_index(self.index, str(self.index_path))
        conn = self._connect()
        try:
            conn.executemany("INSERT INTO vectors (doc_id, chunk_id) VALUES (?, ?)", keys)
            conn.commit()
        finally:
            conn.close()
        self.keys.extend(keys)

    # ------------------------------------------------------------------- query
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Tuple[int, float]]:
        if self.index is None:
            return []
        query = query_vector.reshape(1, -1).astype(np.float32)
        scores, indices = self.index.search(query, top_k)
        hits: List[Tuple[int, float]] = []
        for idx, score in zip(indices[0], scores[0]):
            if idx == -1:
                continue
            hits.append((int(idx), float(score)))
        return hits

    def key_for_index(self, idx: int) -> Optional[Tuple[str, int]]:
        if idx < 0 or idx >= len(self.keys):
            return None
        return self.keys[idx]

    def vector_for_index(self, idx: int) -> Optional[np.ndarray]:
        if self.index is None or idx < 0 or idx >= self.index.ntotal:
            return None
        return self.index.reconstruct(idx)

    def size(self) -> int:
        return len(self.keys)

    # ------------------------------------------------------------------- admin
    def drop(self) -> None:
        for path in (self.index_path, self.sqlite_path, self.manifest_path):
            if path.exists():
                if path.is_file():
                    path.unlink()
                else:
                    shutil.rmtree(path)
        self.index = None
        self.keys = []
        self.manifest = None


__all__ = ["FAISSVectorStore"]

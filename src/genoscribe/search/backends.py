from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Type

from genoscribe.indexing import DocumentIndex, LibraryStats, Passage
from genoscribe.retrieval import search_library


@dataclass
class SearchRequest:
    """Simple envelope so future metadata can be attached to search calls."""

    query: str
    top_k: int
    filters: Optional[Dict[str, str]] = None


class SearchBackend:
    """Base class for pluggable search implementations."""

    name: str = "base"

    def search(
        self,
        library: List[DocumentIndex],
        stats: Optional[LibraryStats],
        request: SearchRequest,
    ) -> List[Passage]:
        raise NotImplementedError


class BM25SearchBackend(SearchBackend):
    name = "bm25"

    def search(
        self,
        library: List[DocumentIndex],
        stats: Optional[LibraryStats],
        request: SearchRequest,
    ) -> List[Passage]:
        if not stats:
            return []
        return search_library(
            library=library,
            query=request.query,
            idf_weights=stats.idf_weights,
            avg_doc_length=stats.avg_doc_length,
            method="bm25",
            top_k=request.top_k,
        )


class TFIDFSearchBackend(SearchBackend):
    name = "tfidf"

    def search(
        self,
        library: List[DocumentIndex],
        stats: Optional[LibraryStats],
        request: SearchRequest,
    ) -> List[Passage]:
        if not stats:
            return []
        return search_library(
            library=library,
            query=request.query,
            idf_weights=stats.idf_weights,
            avg_doc_length=stats.avg_doc_length,
            method="tfidf",
            top_k=request.top_k,
        )


class SearchBackendRegistry:
    """Lightweight registry so future custom backends can be plugged in."""

    def __init__(self) -> None:
        self._backends: Dict[str, SearchBackend] = {}
        self.register(BM25SearchBackend())
        self.register(TFIDFSearchBackend())

    def register(self, backend: SearchBackend) -> None:
        self._backends[backend.name] = backend

    def get(self, name: str) -> SearchBackend:
        return self._backends.get(name, self._backends["bm25"])

    def available(self) -> List[str]:
        return list(self._backends.keys())

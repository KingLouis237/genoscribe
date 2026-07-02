from __future__ import annotations

from __future__ import annotations

import sys
from types import ModuleType

from genoscribe.config import LIBRARY_DIR
from genoscribe.indexing.chunker import build_index_for_file
from genoscribe.indexing.sparse_index import (
    bm25_score,
    calculate_avg_doc_length,
    calculate_idf,
    cosine_sim,
    tf_vector,
    tfidf_vector,
    tokenize,
)
from genoscribe.schemas.document import DocumentIndex, LibraryStats, Passage
from genoscribe.storage.provenance_store import (
    AssistantState,
    library_requires_stats_rebuild,
    load_library,
    load_library_stats,
    load_state,
    rebuild_library_stats,
    save_doc_index,
    save_library_stats,
    save_state,
)
from genoscribe.storage import provenance_store as _prov

__all__ = [
    "LIBRARY_DIR",
    "AssistantState",
    "DocumentIndex",
    "LibraryStats",
    "Passage",
    "build_index_for_file",
    "library_requires_stats_rebuild",
    "load_library",
    "load_library_stats",
    "load_state",
    "rebuild_library_stats",
    "save_doc_index",
    "save_library_stats",
    "save_state",
    "bm25_score",
    "calculate_avg_doc_length",
    "calculate_idf",
    "cosine_sim",
    "tf_vector",
    "tfidf_vector",
    "tokenize",
]


class _IndexingModule(ModuleType):
    def __setattr__(self, name: str, value) -> None:
        if name == "LIBRARY_DIR":
            setattr(_prov, "LIBRARY_DIR", value)
        super().__setattr__(name, value)


module = sys.modules[__name__]
module.__class__ = _IndexingModule  # type: ignore[misc]

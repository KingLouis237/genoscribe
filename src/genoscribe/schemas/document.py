from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DocumentMetadata:
    """Lightweight metadata captured for every ingested document."""

    doc_id: str
    source_path: str
    title: str
    ext: str
    pages: Optional[int] = None
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class Passage:
    doc_id: str
    source_path: str
    page: Optional[int]
    chunk_id: int
    text: str
    is_table_or_figure: bool = False
    raw_text: Optional[str] = None
    summary: Optional[str] = None
    noise_level: float = 0.0
    metrics: List[Dict[str, str]] = field(default_factory=list)
    chunk_type: str = "unknown"
    doc_type: str = "paper"
    short_tokens: List[str] = field(default_factory=list)


@dataclass
class DocumentIndex:
    doc_id: str
    source_path: str
    ext: str
    title: str
    passages: List[Passage]
    vectors: List[Dict[str, float]]
    term_counts: List[Dict[str, int]]
    doc_lengths: List[int]
    doc_type: str = "paper"


@dataclass
class LibraryStats:
    idf_weights: Dict[str, float]
    avg_doc_length: float
    total_docs: int
    total_passages: int
    last_updated: str


__all__ = [
    "DocumentMetadata",
    "Passage",
    "DocumentIndex",
    "LibraryStats",
]

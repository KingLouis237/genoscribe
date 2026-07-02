from __future__ import annotations

import pathlib
from typing import Dict, List, Optional, Tuple

from genoscribe.indexing import (
    DocumentIndex,
    Passage,
    bm25_score,
    cosine_sim,
    tfidf_vector,
    tokenize,
)


def search_library_tfidf(
    library: List[DocumentIndex],
    query: str,
    idf_weights: Dict[str, float],
    top_k: int = 6,
) -> List[Passage]:
    qv = tfidf_vector(query, idf_weights)
    scored: List[Tuple[float, Passage]] = []

    for doc in library:
        for vec, pas in zip(doc.vectors, doc.passages):
            s = cosine_sim(qv, vec)
            if s > 0:
                scored.append((s, pas))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]


def search_library_bm25(
    library: List[DocumentIndex],
    query: str,
    idf_weights: Dict[str, float],
    avg_doc_length: float,
    top_k: int = 6,
) -> List[Passage]:
    query_terms = tokenize(query)
    scored: List[Tuple[float, Passage]] = []

    for doc in library:
        for term_count, doc_len, pas in zip(doc.term_counts, doc.doc_lengths, doc.passages):
            score = bm25_score(
                query_terms=query_terms,
                doc_terms=term_count,
                doc_length=doc_len,
                avg_doc_length=avg_doc_length,
                idf_weights=idf_weights,
            )
            if score > 0:
                scored.append((score, pas))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]


def search_library(
    library: List[DocumentIndex],
    query: str,
    idf_weights: Dict[str, float],
    avg_doc_length: float = 0.0,
    method: str = "bm25",
    top_k: int = 6,
) -> List[Passage]:
    if method == "bm25":
        return search_library_bm25(library, query, idf_weights, avg_doc_length, top_k)
    return search_library_tfidf(library, query, idf_weights, top_k)


def format_citation(p: Passage) -> str:
    loc = f"p.{p.page}" if p.page else "no-page"
    special = " [TABLE/FIG]" if p.is_table_or_figure else ""
    return f"[CITE doc={pathlib.Path(p.source_path).name} {loc} chunk={p.chunk_id}{special}]"


def build_evidence_block(passages: List[Passage], max_items: int = 6) -> str:
    parts: List[str] = []
    for p in passages[:max_items]:
        parts.append(f"{format_citation(p)}\n{p.text}\n")
    return "\n\n".join(parts).strip()


def get_passage_by_index(
    library: List[DocumentIndex],
    passage_ref: Passage,
) -> Tuple[Optional[DocumentIndex], int]:
    for doc in library:
        if doc.doc_id == passage_ref.doc_id:
            for i, p in enumerate(doc.passages):
                if p.chunk_id == passage_ref.chunk_id and p.page == passage_ref.page:
                    return doc, i
    return None, -1


def expand_passage(
    library: List[DocumentIndex],
    passage_ref: Passage,
    radius: int = 1,
) -> List[Passage]:
    doc, idx = get_passage_by_index(library, passage_ref)
    if doc is None or idx < 0:
        return [passage_ref]

    start = max(0, idx - radius)
    end = min(len(doc.passages), idx + radius + 1)
    return doc.passages[start:end]
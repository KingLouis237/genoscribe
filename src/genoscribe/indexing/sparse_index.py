from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

from genoscribe.config import BM25_B, BM25_K1
from genoscribe.schemas.document import DocumentIndex, Passage

from ..ingestion.sectionizer import normalize_genomics_text


def tokenize(text: str) -> List[str]:
    text = normalize_genomics_text(text).lower()
    text = re.sub(r"[^a-z0-9_+\-./ ]+", " ", text)
    toks = [t for t in text.split() if len(t) >= 2]
    return toks


def tf_vector(text: str) -> Dict[str, float]:
    toks = tokenize(text)
    if not toks:
        return {}

    vec: Dict[str, float] = {}
    for t in toks:
        vec[t] = vec.get(t, 0.0) + 1.0
    return vec


def tfidf_vector(text: str, idf_weights: Dict[str, float]) -> Dict[str, float]:
    vec = tf_vector(text)
    if not vec:
        return {}

    max_tf = max(vec.values()) or 1.0
    for term, tf in list(vec.items()):
        vec[term] = (tf / max_tf) * idf_weights.get(term, 0.0)
    return vec


def cosine_sim(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    if not v1 or not v2:
        return 0.0

    dot = 0.0
    for term, w in v1.items():
        dot += w * v2.get(term, 0.0)

    mag1 = math.sqrt(sum(w * w for w in v1.values()))
    mag2 = math.sqrt(sum(w * w for w in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def bm25_score(
    *,
    query_terms: List[str],
    doc_terms: Dict[str, int],
    doc_length: int,
    avg_doc_length: float,
    idf_weights: Dict[str, float],
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> float:
    score = 0.0
    for term in query_terms:
        tf = doc_terms.get(term)
        if not tf:
            continue
        idf = idf_weights.get(term, 0.0)
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * (doc_length / (avg_doc_length or 1.0)))
        score += idf * (numerator / denominator)
    return score


def calculate_idf(library: List[DocumentIndex]) -> Dict[str, float]:
    if not library:
        return {}

    doc_count: Dict[str, int] = {}
    total_docs = 0
    for doc in library:
        total_docs += 1
        doc_terms = set()
        for passage in doc.passages:
            doc_terms.update(tokenize(passage.text))
        for term in doc_terms:
            doc_count[term] = doc_count.get(term, 0) + 1

    idf_weights: Dict[str, float] = {}
    for term, df in doc_count.items():
        idf_weights[term] = math.log((total_docs + 1) / (df + 1))
    return idf_weights


def calculate_avg_doc_length(library: List[DocumentIndex]) -> float:
    if not library:
        return 0.0

    total_length = 0
    total_passages = 0
    for doc in library:
        for passage in doc.passages:
            total_length += len(tokenize(passage.text))
            total_passages += 1
    return total_length / total_passages if total_passages else 0.0


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


__all__ = [
    "tokenize",
    "tf_vector",
    "tfidf_vector",
    "cosine_sim",
    "bm25_score",
    "calculate_idf",
    "calculate_avg_doc_length",
    "search_library",
]

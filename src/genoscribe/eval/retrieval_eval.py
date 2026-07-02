from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from genoscribe.schemas.document import Passage


@dataclass
class RetrievalEvalResult:
    query: str
    precision_at_k: float
    recall_at_k: float


def evaluate_retrieval(queries: List[str], corpus: Dict[str, List[Passage]]) -> List[RetrievalEvalResult]:
    results: List[RetrievalEvalResult] = []
    for query in queries:
        passages = corpus.get(query, [])
        p_at_k = min(1.0, len(passages) / 5) if passages else 0.0
        results.append(RetrievalEvalResult(query=query, precision_at_k=p_at_k, recall_at_k=p_at_k))
    return results


__all__ = ["RetrievalEvalResult", "evaluate_retrieval"]

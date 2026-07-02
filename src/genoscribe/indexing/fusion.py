from __future__ import annotations

from typing import List, Sequence

from genoscribe.schemas.document import Passage


def reciprocal_rank_fusion(runs: Sequence[List[Passage]], k: int = 60) -> List[Passage]:
    scores: dict[str, float] = {}
    seen: dict[str, Passage] = {}

    for run in runs:
        for rank, passage in enumerate(run, start=1):
            key = f"{passage.doc_id}:{passage.chunk_id}:{passage.page}"
            seen[key] = passage
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [seen[key] for key, _ in ordered]


__all__ = ["reciprocal_rank_fusion"]

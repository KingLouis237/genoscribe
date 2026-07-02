from __future__ import annotations

from typing import List

from genoscribe.schemas.evidence import EvidenceSet, EvidenceSpan
from genoscribe.schemas.paper import PaperClaim, PaperSynthesis
from genoscribe.schemas.document import Passage

from ..ingestion.table_figure_extractor import build_passage_summary


def build_paper_synthesis(passages: List[Passage], title: str) -> PaperSynthesis:
    claims: List[PaperClaim] = []
    for passage in passages:
        summary = build_passage_summary(passage.text, passage.is_table_or_figure) or passage.text[:280]
        evidence = EvidenceSet(spans=[EvidenceSpan(passage=passage, label="claim")], confidence=0.7)
        claims.append(PaperClaim(statement=summary, evidence=evidence, limitations=[]))
    return PaperSynthesis(title=title, claims=claims, unresolved_questions=[])


__all__ = ["build_paper_synthesis"]

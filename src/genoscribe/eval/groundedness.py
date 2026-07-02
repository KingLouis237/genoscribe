from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

from genoscribe.schemas.evidence import EvidenceSet


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if len(tok) > 2}


def _evidence_text(evidence: EvidenceSet) -> str:
    chunks = []
    for span in evidence.spans:
        if span.passage and span.passage.text:
            chunks.append(span.passage.text)
    return " ".join(chunks)


@dataclass
class GroundednessJudgeResult:
    score: int
    coverage: float
    rationale: str


def score_groundedness(answer: str, evidence: EvidenceSet) -> GroundednessJudgeResult:
    answer_tokens = _tokenize(answer)
    evidence_tokens = _tokenize(_evidence_text(evidence))
    if not answer_tokens:
        return GroundednessJudgeResult(score=1, coverage=0.0, rationale="No answer tokens to evaluate.")
    overlap = len(answer_tokens & evidence_tokens)
    coverage = overlap / max(len(answer_tokens), 1)
    if coverage >= 0.6:
        score = 5
        rationale = "Fully supported by cited passages."
    elif coverage >= 0.3:
        score = 3
        rationale = "Partially supported; fill gaps or cite additional evidence."
    else:
        score = 1
        rationale = "Statements lack alignment with provided evidence."
    return GroundednessJudgeResult(score=score, coverage=coverage, rationale=rationale)


__all__ = ["GroundednessJudgeResult", "score_groundedness"]

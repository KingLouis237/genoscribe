from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from genoscribe.eval.groundedness import GroundednessJudgeResult, score_groundedness
from genoscribe.schemas.evidence import EvidenceSet

@dataclass
class AnswerEvalResult:
    run_id: str
    faithfulness: float
    unsupported_claim_rate: float
    groundedness: float = 0.0
    groundedness_notes: str = ""


def evaluate_answers(
    responses: List[str],
    evidences: Optional[List[EvidenceSet]] = None,
) -> AnswerEvalResult:
    if not responses:
        return AnswerEvalResult(run_id="n/a", faithfulness=0.0, unsupported_claim_rate=1.0)
    avg_length = sum(len(r.split()) for r in responses) / len(responses)
    faithfulness = min(1.0, avg_length / 200)
    unsupported_rate = max(0.0, 1.0 - faithfulness)
    grounded_scores: List[GroundednessJudgeResult] = []
    if evidences and len(evidences) == len(responses):
        grounded_scores = [score_groundedness(resp, ev) for resp, ev in zip(responses, evidences)]
    grounded_avg = sum(gs.score for gs in grounded_scores) / len(grounded_scores) if grounded_scores else 0.0
    grounded_notes = "; ".join(gs.rationale for gs in grounded_scores[:3]) if grounded_scores else ""
    return AnswerEvalResult(
        run_id="default",
        faithfulness=faithfulness,
        unsupported_claim_rate=unsupported_rate,
        groundedness=grounded_avg,
        groundedness_notes=grounded_notes,
    )


__all__ = ["AnswerEvalResult", "evaluate_answers"]

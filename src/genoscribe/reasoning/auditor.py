from __future__ import annotations

from typing import List

from genoscribe.extraction.contradiction import detect_contradictions
from genoscribe.schemas.evidence import EvidenceSet


class EvidenceAuditor:
    def audit(self, evidence_sets: List[EvidenceSet]) -> List[str]:
        return detect_contradictions(evidence_sets)


__all__ = ["EvidenceAuditor"]

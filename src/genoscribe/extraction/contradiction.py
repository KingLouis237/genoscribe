from __future__ import annotations

from typing import List

from genoscribe.schemas.evidence import EvidenceSet


def detect_contradictions(evidence_sets: List[EvidenceSet]) -> List[str]:
    warnings: List[str] = []
    seen: set[str] = set()
    for evidence in evidence_sets:
        for span in evidence.spans:
            key = (span.metadata or {}).get("label") or span.label
            if key in seen:
                warnings.append(f"Conflicting statements detected for label '{key}'.")
            else:
                seen.add(key)
    return warnings


__all__ = ["detect_contradictions"]

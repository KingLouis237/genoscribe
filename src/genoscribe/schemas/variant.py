from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .evidence import EvidenceSet


@dataclass
class CohortContext:
    cohort: str
    ancestry: Optional[str] = None
    sample_size: Optional[int] = None
    notes: Optional[str] = None


@dataclass
class VariantAssessment:
    variant_id: str
    effect: Optional[str] = None
    phenotype: Optional[str] = None
    cohorts: List[CohortContext] = field(default_factory=list)
    evidence: List[EvidenceSet] = field(default_factory=list)
    uncertainty: Optional[str] = None


__all__ = ["CohortContext", "VariantAssessment"]

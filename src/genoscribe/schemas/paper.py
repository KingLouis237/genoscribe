from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .evidence import EvidenceSet


@dataclass
class PaperClaim:
    statement: str
    evidence: EvidenceSet
    limitations: List[str] = field(default_factory=list)


@dataclass
class PaperSynthesis:
    title: str
    claims: List[PaperClaim]
    unresolved_questions: List[str] = field(default_factory=list)


__all__ = ["PaperClaim", "PaperSynthesis"]

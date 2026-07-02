from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .document import Passage


@dataclass
class EvidenceSpan:
    passage: Passage
    label: str
    start_char: int = 0
    end_char: int = 0
    score: float = 0.0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class EvidenceSet:
    """Structured evidence bundle traced back to one or more passages."""

    spans: List[EvidenceSpan]
    confidence: float = 0.0
    rationale: Optional[str] = None


__all__ = ["EvidenceSpan", "EvidenceSet"]

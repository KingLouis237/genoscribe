from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .evidence import EvidenceSet


@dataclass
class AssemblyMetric:
    name: str
    value: str
    tool: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class AssemblyQCReport:
    sample_id: Optional[str]
    metrics: List[AssemblyMetric] = field(default_factory=list)
    narrative: Optional[str] = None
    evidence: List[EvidenceSet] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


__all__ = ["AssemblyMetric", "AssemblyQCReport"]

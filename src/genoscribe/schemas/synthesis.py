from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from genoscribe.reasoning.evidence_bundle import CoverageReport


@dataclass
class CitationRef:
    doc_id: str
    source_path: str
    chunk_id: int
    page: Optional[int] = None


@dataclass
class MetricSummary:
    id: str
    metric_label: str
    value: str
    model: str
    dataset: str
    task: str
    citation: CitationRef


@dataclass
class SupportedClaim:
    id: str
    statement: str
    support_status: str  # supported | partially_supported | conflicting_evidence
    support_strength: str
    support_reason: str
    evidence_quality: str
    citations: List[CitationRef] = field(default_factory=list)
    related_metrics: List[str] = field(default_factory=list)


@dataclass
class UnsupportedClaim:
    id: str
    topic: str
    requested_terms: List[str]
    reason: str
    status: str  # insufficient_evidence
    suggested_action: str


@dataclass
class LimitationNote:
    id: str
    kind: str
    description: str
    citations: List[CitationRef] = field(default_factory=list)


@dataclass
class ConflictSet:
    id: str
    conflict_type: str
    description: str
    status: str  # conflicting_evidence
    citation_refs: List[CitationRef] = field(default_factory=list)
    related_claim_ids: List[str] = field(default_factory=list)


@dataclass
class RetrievalCandidate:
    doc_id: str
    source_path: str
    chunk_id: int
    page: Optional[int]
    chunk_type: str
    summary: str
    kept: bool = True
    filter_reason: str = "structured_pipeline"


@dataclass
class SynthesisAudit:
    render_status: str  # supported | partially_supported | insufficient_evidence | conflicting_evidence | off_target_evidence
    verifier_notes: List[str] = field(default_factory=list)
    dropped_claim_ids: List[str] = field(default_factory=list)


@dataclass
class StructuredPaperSynthesis:
    title: str
    query: Optional[str]
    retrieval_candidates: List[RetrievalCandidate]
    supported_claims: List[SupportedClaim]
    unsupported_claims: List[UnsupportedClaim]
    limitations: List[LimitationNote]
    metric_summaries: List[MetricSummary]
    coverage: CoverageReport
    conflicts: List[ConflictSet]
    audit: SynthesisAudit


__all__ = [
    "CitationRef",
    "MetricSummary",
    "SupportedClaim",
    "UnsupportedClaim",
    "LimitationNote",
    "ConflictSet",
    "RetrievalCandidate",
    "SynthesisAudit",
    "StructuredPaperSynthesis",
]

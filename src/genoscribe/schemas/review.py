from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from genoscribe.schemas.document import Passage
from genoscribe.schemas.synthesis import StructuredPaperSynthesis


@dataclass
class CandidateView:
    doc_id: str
    source_path: str
    chunk_id: int
    page: Optional[int]
    chunk_type: str
    doc_type: str
    summary: str
    fused_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rerank_score: Optional[float] = None
    kept: bool = True
    final_rank: Optional[int] = None

    @property
    def doc_name(self) -> str:
        return Path(self.source_path).name


@dataclass
class PassageMetadata:
    doc_id: str
    source_path: str
    chunk_id: int
    page: Optional[int]
    chunk_type: str
    doc_type: str
    noise_level: float
    has_metrics: bool
    is_table_or_figure: bool


@dataclass
class FilterTrace:
    fused_score: float
    mode_boost: float
    noise_penalty: float
    query_overlap: float
    informative_overlap: float
    query_weight: float
    duplicate_of: Optional[str]
    figure_quota_hit: bool
    kept: bool
    reason: str


@dataclass
class MetricRow:
    label: str
    value: str
    model: str
    task: str
    dataset: str
    chunk_id: int
    chunk_type: str
    doc_id: str
    source_path: str
    page: Optional[int]
    context: str
    confidence: float
    confidence_reason: str


@dataclass
class EvidenceBundlePreview:
    bundle_type: str
    coverage_notes: List[str] = field(default_factory=list)
    coverage_counts: Dict[str, int] = field(default_factory=dict)
    contradictions: List[str] = field(default_factory=list)
    unresolved_requests: List[str] = field(default_factory=list)


@dataclass
class StructuredAnswerView:
    mode: str
    structured: Optional[StructuredPaperSynthesis]
    rendered_text: str
    audit_status: str
    verifier_notes: List[str] = field(default_factory=list)


@dataclass
class DiagnosticsReport:
    timings_ms: Dict[str, float]
    cache_stats: Dict[str, float]
    stage_hits: Dict[str, List[str]]
    benchmark_artifacts: List[str] = field(default_factory=list)


@dataclass
class ReviewQueryResult:
    mode: str
    query: str
    rewritten_query: str
    candidates: List[CandidateView]
    passage_map: Dict[str, Passage]
    metadata: Dict[str, PassageMetadata]
    filter_traces: Dict[str, FilterTrace]
    metrics: List[MetricRow]
    bundle_preview: EvidenceBundlePreview
    structured_answer: StructuredAnswerView
    diagnostics: DiagnosticsReport
    target_doc_ids: List[str] = field(default_factory=list)


__all__ = [
    "CandidateView",
    "PassageMetadata",
    "FilterTrace",
    "MetricRow",
    "EvidenceBundlePreview",
    "StructuredAnswerView",
    "DiagnosticsReport",
    "ReviewQueryResult",
]

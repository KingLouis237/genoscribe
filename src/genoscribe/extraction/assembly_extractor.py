from __future__ import annotations

from typing import List, Optional

from genoscribe.schemas.assembly import AssemblyMetric, AssemblyQCReport
from genoscribe.schemas.evidence import EvidenceSet, EvidenceSpan
from genoscribe.schemas.document import Passage


def build_assembly_qc_report(passages: List[Passage], sample_id: Optional[str] = None) -> AssemblyQCReport:
    metrics: List[AssemblyMetric] = []
    spans: List[EvidenceSpan] = []

    for p in passages:
        for line in p.text.splitlines():
            if ":" in line and len(line) < 120:
                name, value = [seg.strip() for seg in line.split(":", 1)]
                metrics.append(AssemblyMetric(name=name, value=value, tool="text"))
        spans.append(EvidenceSpan(passage=p, label="assembly"))

    evidence = EvidenceSet(spans=spans, confidence=0.5 if spans else 0.0)
    narrative = "Summarized QC metrics from retrieved evidence."
    warnings = [] if metrics else ["No explicit QC metrics detected; inspect passages manually."]

    return AssemblyQCReport(
        sample_id=sample_id,
        metrics=metrics,
        narrative=narrative,
        evidence=[evidence] if spans else [],
        warnings=warnings,
    )


__all__ = ["build_assembly_qc_report"]

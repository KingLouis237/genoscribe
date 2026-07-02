from __future__ import annotations

from typing import List, Optional

from genoscribe.extraction.assembly_extractor import build_assembly_qc_report
from genoscribe.schemas.document import Passage


class AssemblyMode:
    def generate(self, passages: List[Passage], sample_id: Optional[str] = None) -> str:
        report = build_assembly_qc_report(passages, sample_id)
        lines = [f"Assembly QC report for {sample_id or 'sample'}"]
        for metric in report.metrics:
            lines.append(f"- {metric.name}: {metric.value}")
        if report.warnings:
            lines.append("Warnings:")
            lines.extend(f"  * {warn}" for warn in report.warnings)
        return "\n".join(lines)


__all__ = ["AssemblyMode"]

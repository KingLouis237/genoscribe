from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from genoscribe.extraction.variant_extractor import extract_variant_assessment
from genoscribe.reasoning.evidence_bundle import VariantCandidate
from genoscribe.schemas.document import Passage


def _format_candidate(candidate: VariantCandidate) -> List[str]:
    source_name = Path(candidate.source_path).name
    header = (
        f"- {candidate.variant_id} ({candidate.gene})"
        if candidate.variant_id != "Unknown"
        else f"- Gene context: {candidate.gene}"
    )
    header += f" · {candidate.clinvar_significance}"
    lines = [header]
    lines.append(
        f"  Source: {source_name} · chunk {candidate.chunk_id} · page {candidate.page or 'n/a'} "
        f"[{candidate.chunk_type}/{candidate.doc_type}] · conf={candidate.confidence:.2f} ({candidate.confidence_reason})"
    )
    phenotype_bits: List[str] = []
    if candidate.phenotype != "Unknown":
        phenotype_bits.append(candidate.phenotype)
    if candidate.disease != "Unknown" and candidate.disease != candidate.phenotype:
        phenotype_bits.append(candidate.disease)
    if phenotype_bits:
        lines.append("  Phenotype: " + ", ".join(phenotype_bits))
    context_bits: List[str] = []
    if candidate.cohort != "Unknown":
        context_bits.append(candidate.cohort)
    if candidate.ancestry != "Unknown":
        context_bits.append(candidate.ancestry)
    if candidate.case_count is not None:
        context_bits.append(f"cases={candidate.case_count}")
    if candidate.control_count is not None:
        context_bits.append(f"controls={candidate.control_count}")
    if candidate.gnomad_frequency != "Unknown":
        context_bits.append(f"gnomAD={candidate.gnomad_frequency}")
    if context_bits:
        lines.append("  Context: " + "; ".join(context_bits))
    if candidate.short_token_hits:
        lines.append("  Short-token hints: " + ", ".join(candidate.short_token_hits))
    for metric in candidate.pathogenicity_metrics[:3]:
        lines.append(
            f"  Metric: {metric.label}={metric.value} ({metric.model}, {metric.dataset}, {metric.task}) "
            f"[{metric.chunk_type}]"
        )
    lines.append("  Excerpt: " + candidate.text_excerpt)
    return lines


class VariantMode:
    def generate(
        self,
        passages: List[Passage],
        variant_id: Optional[str] = None,
        phenotype: Optional[str] = None,
        query: Optional[str] = None,
    ) -> str:
        bundle = extract_variant_assessment(passages, variant_id, phenotype, query)
        heading_variant = variant_id or "Unknown variant"
        lines = [f"# Variant evidence for {heading_variant}"]
        if phenotype:
            lines.append(f"Phenotype hint: {phenotype}")
        if not bundle.candidates:
            lines.append("No provenance-backed variant passages satisfied the quality filters.")
        else:
            lines.append("## Evidence")
            for candidate in bundle.candidates:
                lines.extend(_format_candidate(candidate))
        lines.append("")
        lines.append("## Coverage")
        lines.append(
            f"- Passages reviewed: {bundle.coverage.total_passages} | "
            f"Variant-grounded: {bundle.coverage.variant_candidates}"
        )
        if bundle.coverage.missing_fields:
            lines.append("- Missing fields: " + ", ".join(bundle.coverage.missing_fields))
        if bundle.coverage.uncovered_requests:
            lines.append("- Uncovered query terms: " + ", ".join(bundle.coverage.uncovered_requests))
        for note in bundle.coverage.notes:
            lines.append(f"- Note: {note}")
        if bundle.contradictions:
            lines.append("\n## Contradictions")
            for warning in bundle.contradictions:
                lines.append(f"- {warning}")
        return "\n".join(lines).strip()


__all__ = ["VariantMode"]

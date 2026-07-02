from __future__ import annotations

from typing import List, Optional

from genoscribe.config import USE_STRUCTURED_PAPER_SYNTHESIS
from genoscribe.extraction.paper_extractor import build_paper_synthesis
from genoscribe.reasoning.evidence_bundle import assemble_paper_evidence
from genoscribe.reasoning.structured_synthesizer import (
    PaperStructuredRenderer,
    StructuredPaperSynthesizer,
    StructuredVerifier,
)
from genoscribe.schemas.document import Passage


class PaperMode:
    """Mode-specific renderer for paper summaries."""

    def __init__(self) -> None:
        self._structured = StructuredPaperSynthesizer()
        self._verifier = StructuredVerifier()
        self._renderer = PaperStructuredRenderer()

    def generate(
        self,
        passages: List[Passage],
        title: str = "Paper synthesis",
        query: str | None = None,
        target_doc_ids: Optional[List[str]] = None,
    ) -> str:
        bundle = assemble_paper_evidence(passages, query=query, target_doc_ids=target_doc_ids)
        if USE_STRUCTURED_PAPER_SYNTHESIS:
            structured = self._structured.build(bundle, title=title, query=query)
            verified = self._verifier.verify(structured)
            return self._renderer.render(verified)

        synthesis = build_paper_synthesis(passages, title)
        lines = [f"# {synthesis.title}"]
        for idx, claim in enumerate(synthesis.claims, start=1):
            lines.append(f"{idx}. {claim.statement}")
        if synthesis.unresolved_questions:
            lines.append("\nOpen questions:")
            lines.extend(f"- {q}" for q in synthesis.unresolved_questions)
        lines.append(
            f"\nEvidence coverage: {bundle.coverage.total_passages} passages "
            f"({bundle.coverage.figure_passages} figure/table), "
            f"{bundle.coverage.metric_candidates} structured metrics"
        )
        for note in bundle.coverage.notes:
            lines.append(f"- {note}")
        return "\n".join(lines)

    def generate_structured(
        self,
        passages: List[Passage],
        title: str,
        query: Optional[str] = None,
        target_doc_ids: Optional[List[str]] = None,
    ):
        bundle = assemble_paper_evidence(passages, query=query, target_doc_ids=target_doc_ids)
        structured = self._structured.build(bundle, title=title, query=query)
        return self._verifier.verify(structured)


__all__ = ["PaperMode"]

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from genoscribe.reasoning.structured_synthesizer import PaperStructuredRenderer
from genoscribe.schemas.synthesis import (
    CitationRef,
    ConflictSet,
    LimitationNote,
    MetricSummary,
    RetrievalCandidate,
    StructuredPaperSynthesis,
    SupportedClaim,
    SynthesisAudit,
    UnsupportedClaim,
)
from genoscribe.reasoning.evidence_bundle import CoverageReport


def citation_from_dict(data: dict) -> CitationRef:
    return CitationRef(**data)


def metric_from_dict(data: dict) -> MetricSummary:
    citation = citation_from_dict(data["citation"])
    return MetricSummary(
        id=data["id"],
        metric_label=data["metric_label"],
        value=data["value"],
        model=data["model"],
        dataset=data["dataset"],
        task=data["task"],
        citation=citation,
    )


def claim_from_dict(data: dict) -> SupportedClaim:
    citations = [citation_from_dict(item) for item in data.get("citations", [])]
    return SupportedClaim(
        id=data["id"],
        statement=data["statement"],
        support_status=data["support_status"],
        support_strength=data["support_strength"],
        support_reason=data["support_reason"],
        evidence_quality=data["evidence_quality"],
        citations=citations,
        related_metrics=data.get("related_metrics", []),
    )


def unsupported_from_dict(data: dict) -> UnsupportedClaim:
    return UnsupportedClaim(
        id=data["id"],
        topic=data["topic"],
        requested_terms=data.get("requested_terms", []),
        reason=data["reason"],
        status=data["status"],
        suggested_action=data["suggested_action"],
    )


def limitation_from_dict(data: dict) -> LimitationNote:
    return LimitationNote(
        id=data["id"],
        kind=data["kind"],
        description=data["description"],
        citations=[citation_from_dict(item) for item in data.get("citations", [])],
    )


def conflict_from_dict(data: dict) -> ConflictSet:
    return ConflictSet(
        id=data["id"],
        conflict_type=data["conflict_type"],
        description=data["description"],
        status=data["status"],
        citation_refs=[citation_from_dict(item) for item in data.get("citation_refs", [])],
        related_claim_ids=data.get("related_claim_ids", []),
    )


def retrieval_from_dict(data: dict) -> RetrievalCandidate:
    return RetrievalCandidate(
        doc_id=data["doc_id"],
        source_path=data["source_path"],
        chunk_id=data["chunk_id"],
        page=data.get("page"),
        chunk_type=data.get("chunk_type", "body"),
        summary=data.get("summary", ""),
        kept=data.get("kept", True),
    )


def coverage_from_dict(data: dict) -> CoverageReport:
    return CoverageReport(
        total_passages=data["total_passages"],
        figure_passages=data["figure_passages"],
        metric_candidates=data["metric_candidates"],
        missing_terms=data.get("missing_terms", []),
        notes=data.get("notes", []),
    )


def audit_from_dict(data: dict) -> SynthesisAudit:
    return SynthesisAudit(
        render_status=data["render_status"],
        verifier_notes=data.get("verifier_notes", []),
        dropped_claim_ids=data.get("dropped_claim_ids", []),
    )


def structured_from_json(path: Path) -> StructuredPaperSynthesis:
    data = json.loads(path.read_text(encoding="utf-8"))
    return StructuredPaperSynthesis(
        title=data["title"],
        query=data.get("query"),
        retrieval_candidates=[retrieval_from_dict(item) for item in data.get("retrieval_candidates", [])],
        supported_claims=[claim_from_dict(item) for item in data.get("supported_claims", [])],
        unsupported_claims=[unsupported_from_dict(item) for item in data.get("unsupported_claims", [])],
        limitations=[limitation_from_dict(item) for item in data.get("limitations", [])],
        metric_summaries=[metric_from_dict(item) for item in data.get("metric_summaries", [])],
        coverage=coverage_from_dict(data["coverage"]),
        conflicts=[conflict_from_dict(item) for item in data.get("conflicts", [])],
        audit=audit_from_dict(data["audit"]),
    )


def render_gui(structured: StructuredPaperSynthesis, prose: str) -> None:
    console = Console()
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=12),
        Layout(name="middle", size=18),
        Layout(name="bottom"),
    )
    layout["top"].split_row(
        Layout(name="query"),
        Layout(name="coverage"),
    )
    layout["middle"].split_row(
        Layout(name="claims"),
        Layout(name="retrieval"),
    )
    layout["bottom"].split_row(
        Layout(name="conflicts"),
        Layout(name="prose"),
    )

    query_text = structured.query or "n/a"
    layout["query"].update(Panel(query_text, title="Query"))

    coverage_lines = [
        f"Passages: {structured.coverage.total_passages}",
        f"Figure/table: {structured.coverage.figure_passages}",
        f"Metrics: {structured.coverage.metric_candidates}",
        f"Missing terms: {', '.join(structured.coverage.missing_terms) or 'None'}",
        *(f"Note: {note}" for note in structured.coverage.notes),
    ]
    layout["coverage"].update(Panel("\n".join(coverage_lines), title="Evidence coverage"))

    claims_table = Table(title="Supported claims", show_lines=True)
    claims_table.add_column("ID")
    claims_table.add_column("Status")
    claims_table.add_column("Statement")
    claims_table.add_column("Citations")
    if structured.supported_claims:
        for claim in structured.supported_claims:
            citations = ", ".join(
                f"{Path(c.source_path).name}:{c.chunk_id}" for c in claim.citations
            ) or "n/a"
            claims_table.add_row(claim.id, claim.support_status, claim.statement, citations)
    else:
        claims_table.add_row("-", "-", "No supported claims", "-")
    layout["claims"].update(claims_table)

    retrieval_table = Table(title="Retrieval candidates", show_lines=True)
    retrieval_table.add_column("Chunk")
    retrieval_table.add_column("Doc")
    retrieval_table.add_column("Type")
    retrieval_table.add_column("Summary")
    for cand in structured.retrieval_candidates:
        retrieval_table.add_row(
            str(cand.chunk_id),
            Path(cand.source_path).name,
            cand.chunk_type,
            cand.summary,
        )
    layout["retrieval"].update(retrieval_table)

    conflicts_lines: List[str] = []
    if structured.conflicts:
        for conflict in structured.conflicts:
            conflicts_lines.append(f"{conflict.description}")
            for citation in conflict.citation_refs:
                conflicts_lines.append(f" - {Path(citation.source_path).name}:{citation.chunk_id}")
    else:
        conflicts_lines.append("None detected.")
    conflicts_lines.append(f"Audit status: {structured.audit.render_status}")
    for note in structured.audit.verifier_notes:
        conflicts_lines.append(f"Verifier note: {note}")
    layout["conflicts"].update(Panel("\n".join(conflicts_lines), title="Conflicts & audit"))

    layout["prose"].update(Panel(prose, title="Rendered prose"))

    console.print(layout)
    interactive_passage_loop(structured)


LIBRARY_DIR = Path("src/genomics_assistant_data/library")


def _load_library_doc(doc_id: str) -> dict:
    path = LIBRARY_DIR / f"{doc_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No library record for {doc_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def interactive_passage_loop(structured: StructuredPaperSynthesis) -> None:
    console = Console()
    doc_cache: Dict[str, dict] = {}
    if not structured.retrieval_candidates:
        return
    console.print("\n[bold]Interactive passage viewer[/bold]")
    console.print("Enter the retrieval index shown above to inspect the raw passage (q to exit).")
    while True:
        choice = Prompt.ask("Candidate index (q to quit)", default="q")
        if choice.lower() in {"q", "quit", ""}:
            break
        if not choice.isdigit():
            console.print("[red]Please enter a numeric index.[/red]")
            continue
        idx = int(choice) - 1
        if idx < 0 or idx >= len(structured.retrieval_candidates):
            console.print("[red]Index out of range.[/red]")
            continue
        candidate = structured.retrieval_candidates[idx]
        try:
            doc = doc_cache.setdefault(candidate.doc_id, _load_library_doc(candidate.doc_id))
        except FileNotFoundError as exc:
            console.print(f"[red]{exc}[/red]")
            continue
        passage = next((p for p in doc.get("passages", []) if p.get("chunk_id") == candidate.chunk_id), None)
        if passage is None:
            console.print("[red]Chunk not found in library file.[/red]")
            continue
        text = passage.get("text") or ""
        metadata = [
            f"Doc: {candidate.doc_id}",
            f"Source: {Path(candidate.source_path).name}",
            f"Chunk: {candidate.chunk_id}",
            f"Page: {candidate.page or passage.get('page') or 'n/a'}",
            f"Chunk type: {passage.get('chunk_type') or candidate.chunk_type}",
            f"Doc type: {passage.get('doc_type', 'paper')}",
            f"Filter reason: {candidate.filter_reason}",
        ]
        panel_text = "\n".join(metadata) + "\n\n" + text
        console.print(Panel(panel_text, title=f"Passage {idx + 1}"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Review structured paper synthesis output.")
    parser.add_argument("json_path", type=Path, help="Path to structured JSON artifact.")
    args = parser.parse_args()
    structured = structured_from_json(args.json_path)
    renderer = PaperStructuredRenderer()
    prose = renderer.render(structured)
    render_gui(structured, prose)


if __name__ == "__main__":
    main()

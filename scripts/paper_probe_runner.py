from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from rich.console import Console
from rich.table import Table

from genoscribe.app.review_service import EvidenceReviewService
from genoscribe.config import OUTPUT_DIR
from genoscribe.corpus import load_manifest, map_indexed_doc_ids_by_filename

console = Console()


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _load_probe_queries(path: Path) -> Dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    docs = payload.get("documents")
    if not isinstance(docs, list) or not docs:
        raise ValueError("Probe query file must contain a non-empty 'documents' list.")
    return payload


def _expected_doc_ids_for_slug(
    *,
    slug: str,
    manifest_specs,
    indexed_doc_ids_by_filename: Dict[str, List[str]],
) -> List[str]:
    for spec in manifest_specs:
        if spec.slug != slug:
            continue
        return list(indexed_doc_ids_by_filename.get(spec.filename, []))
    return []


def _render_table(rows: List[Dict[str, object]]) -> None:
    table = Table(show_lines=True, title="Paper corpus probes")
    table.add_column("Slug")
    table.add_column("Task")
    table.add_column("Scope source")
    table.add_column("Audit")
    table.add_column("Target inferred")
    table.add_column("Final overlap")
    table.add_column("Integrity")
    table.add_column("Claims")
    table.add_column("Metrics")
    for row in rows:
        integrity = "blocked" if row["integrity_blocked"] else "ok"
        table.add_row(
            str(row["slug"]),
            str(row["task_type"]),
            str(row["target_scope_source"]),
            str(row["audit_status"]),
            "yes" if row["target_doc_inferred"] else "no",
            "yes" if row["final_doc_overlap"] else "no",
            integrity,
            f"{row['supported_claims']}/{row['unsupported_claims']}",
            str(row["metric_count"]),
        )
    console.print(table)


def _is_paper_primary_probe(modes: Sequence[str]) -> bool:
    mode_set = {str(mode).strip().lower() for mode in modes}
    return "paper" in mode_set and "assembly" not in mode_set and "variant" not in mode_set


def _is_deictic_scoped_query(query: str) -> bool:
    lowered = (query or "").lower()
    return bool(re.search(r"\bthis\b", lowered))


def _probe_integrity_state(
    *,
    paper_primary_probe: bool,
    expected_doc_type: str | None,
    indexed_doc_types: Sequence[str],
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    indexed_set = {doc_type for doc_type in indexed_doc_types if doc_type}
    if paper_primary_probe and indexed_set and any(doc_type != "paper" for doc_type in indexed_set):
        reasons.append("paper_primary_not_indexed_as_paper")
    if expected_doc_type and indexed_set and expected_doc_type not in indexed_set:
        reasons.append(f"expected_doc_type_mismatch:{expected_doc_type}")
    if expected_doc_type and not indexed_set:
        reasons.append("expected_doc_type_unverifiable_no_indexed_doc")
    return bool(reasons), reasons


def run_probes(*, manifest_path: Path, probes_path: Path, top_k: int) -> tuple[Path, Path]:
    manifest_specs = load_manifest(manifest_path)
    probes = _load_probe_queries(probes_path)

    service = EvidenceReviewService(top_k=top_k)
    indexed_by_file = map_indexed_doc_ids_by_filename(service.library)
    manifest_slug_map = {spec.slug: spec for spec in manifest_specs}
    doc_type_by_doc_id = {
        doc.doc_id: (str(getattr(doc, "doc_type", "paper") or "paper").strip().lower())
        for doc in service.library
    }

    rows: List[Dict[str, object]] = []
    for doc_entry in probes["documents"]:
        slug = str(doc_entry.get("slug", "")).strip()
        if slug not in manifest_slug_map:
            raise ValueError(f"Probe slug '{slug}' is not present in manifest.")
        spec = manifest_slug_map[slug]
        queries = doc_entry.get("queries", [])
        if not isinstance(queries, list) or not queries:
            raise ValueError(f"Probe document '{slug}' must contain at least one query.")
        expected_doc_ids = _expected_doc_ids_for_slug(
            slug=slug,
            manifest_specs=manifest_specs,
            indexed_doc_ids_by_filename=indexed_by_file,
        )
        if not expected_doc_ids:
            raise RuntimeError(
                f"No indexed doc_id found for slug '{slug}'. Run corpus_sync with --download-missing --ingest-missing first."
            )
        expected_doc_type = (spec.expected_doc_type or "").strip().lower() or None
        indexed_doc_types = sorted(
            {
                doc_type_by_doc_id.get(doc_id, "")
                for doc_id in expected_doc_ids
                if doc_type_by_doc_id.get(doc_id, "")
            }
        )
        paper_primary_probe = _is_paper_primary_probe(spec.modes)
        integrity_blocked, integrity_reasons = _probe_integrity_state(
            paper_primary_probe=paper_primary_probe,
            expected_doc_type=expected_doc_type,
            indexed_doc_types=indexed_doc_types,
        )

        for query_entry in queries:
            query = str(query_entry.get("query", "")).strip()
            task_type = str(query_entry.get("task_type", "probe")).strip()
            query_id = str(query_entry.get("id", "query")).strip()
            if not query:
                raise ValueError(f"Empty query for slug '{slug}' id '{query_id}'.")

            is_deictic = _is_deictic_scoped_query(query)
            target_override = list(expected_doc_ids) if is_deictic else None
            result = service.run_query(
                query=query,
                mode="paper",
                top_k=top_k,
                target_doc_ids_override=target_override,
            )
            final_doc_ids = [candidate.doc_id for candidate in result.candidates]
            expected_set = set(expected_doc_ids)
            inferred_set = set(result.target_doc_ids)
            final_set = set(final_doc_ids)
            target_inferred = bool(expected_set & inferred_set)
            final_overlap = bool(expected_set & final_set)
            if target_override:
                target_scope_source = "context_override"
            elif result.target_doc_ids:
                target_scope_source = "inferred"
            else:
                target_scope_source = "none"

            structured = result.structured_answer.structured
            supported_claims = len(structured.supported_claims) if structured else 0
            unsupported_claims = len(structured.unsupported_claims) if structured else 0
            limitation_count = len(structured.limitations) if structured else 0
            conflict_count = len(structured.conflicts) if structured else 0
            claim_doc_ids = sorted(
                {
                    citation.doc_id
                    for claim in (structured.supported_claims if structured else [])
                    for citation in claim.citations
                    if citation.doc_id
                }
            )
            top_candidates = [
                {
                    "doc_id": candidate.doc_id,
                    "chunk_id": candidate.chunk_id,
                    "chunk_type": candidate.chunk_type,
                    "doc_type": candidate.doc_type,
                    "fused_score": candidate.fused_score,
                    "summary": candidate.summary,
                }
                for candidate in result.candidates
            ]

            rows.append(
                {
                    "slug": slug,
                    "title": spec.title,
                    "query_id": query_id,
                    "task_type": task_type,
                    "query": query,
                    "manifest_buckets": list(spec.buckets),
                    "manifest_modes": list(spec.modes),
                    "paper_primary_probe": paper_primary_probe,
                    "expected_doc_type": expected_doc_type,
                    "indexed_doc_types": indexed_doc_types,
                    "integrity_blocked": integrity_blocked,
                    "integrity_reasons": integrity_reasons,
                    "expected_doc_ids": expected_doc_ids,
                    "target_doc_ids": result.target_doc_ids,
                    "target_scope_source": target_scope_source,
                    "final_doc_ids": final_doc_ids,
                    "target_doc_inferred": target_inferred,
                    "final_doc_overlap": final_overlap,
                    "audit_status": result.structured_answer.audit_status,
                    "supported_claims": supported_claims,
                    "unsupported_claims": unsupported_claims,
                    "limitations": limitation_count,
                    "conflicts": conflict_count,
                    "metric_count": len(result.metrics),
                    "claim_doc_ids": claim_doc_ids,
                    "coverage_notes": list(result.bundle_preview.coverage_notes),
                    "verifier_notes": list(result.structured_answer.verifier_notes),
                    "timings_ms": dict(result.diagnostics.timings_ms),
                    "top_candidates": top_candidates,
                    "structured_answer": asdict(result.structured_answer),
                }
            )

    summary = {
        "total_queries": len(rows),
        "target_doc_inferred": sum(1 for row in rows if row["target_doc_inferred"]),
        "final_doc_overlap": sum(1 for row in rows if row["final_doc_overlap"]),
        "insufficient_evidence": sum(1 for row in rows if row["audit_status"] == "insufficient_evidence"),
        "off_target_evidence": sum(1 for row in rows if row["audit_status"] == "off_target_evidence"),
        "integrity_blocked_queries": sum(1 for row in rows if row["integrity_blocked"]),
        "paper_primary_queries": sum(1 for row in rows if row["paper_primary_probe"]),
        "target_scope_source_counts": {
            "context_override": sum(1 for row in rows if row["target_scope_source"] == "context_override"),
            "inferred": sum(1 for row in rows if row["target_scope_source"] == "inferred"),
            "none": sum(1 for row in rows if row["target_scope_source"] == "none"),
        },
    }

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "probes_path": str(probes_path),
        "top_k": top_k,
        "summary": summary,
        "rows": rows,
    }

    out_dir = OUTPUT_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    json_path = out_dir / f"paper_probe_report_{stamp}.json"
    csv_path = out_dir / f"paper_probe_summary_{stamp}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "slug",
                "query_id",
                "task_type",
                "audit_status",
                "target_scope_source",
                "target_doc_inferred",
                "final_doc_overlap",
                "integrity_blocked",
                "supported_claims",
                "unsupported_claims",
                "limitations",
                "conflicts",
                "metric_count",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["slug"],
                    row["query_id"],
                    row["task_type"],
                    row["audit_status"],
                    row["target_scope_source"],
                    row["target_doc_inferred"],
                    row["final_doc_overlap"],
                    row["integrity_blocked"],
                    row["supported_claims"],
                    row["unsupported_claims"],
                    row["limitations"],
                    row["conflicts"],
                    row["metric_count"],
                ]
            )

    _render_table(rows)
    console.print(f"[green]Saved probe report:[/green] {json_path}")
    console.print(f"[green]Saved probe summary:[/green] {csv_path}")
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paper-mode corpus probes without touching fixed benchmark matrix.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/corpus/corpus_manifest.json"),
        help="Path to corpus manifest.",
    )
    parser.add_argument(
        "--probes",
        type=Path,
        default=Path("docs/corpus/paper_probe_queries.json"),
        help="Path to paper probe query configuration.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Top-k candidates to keep from hybrid retrieval.",
    )
    args = parser.parse_args()
    run_probes(manifest_path=args.manifest, probes_path=args.probes, top_k=args.top_k)


if __name__ == "__main__":
    main()

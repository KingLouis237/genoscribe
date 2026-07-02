from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console
from rich.table import Table

from genoscribe.app.review_service import EvidenceReviewService
from genoscribe.config import OUTPUT_DIR
from genoscribe.corpus import load_manifest, map_indexed_doc_ids_by_filename
from genoscribe.eval.paper_validation import (
    evaluate_auto_checks,
    load_validation_matrix,
    select_doc_ids_for_slug,
    summarize_results,
    validate_matrix_completeness,
)

console = Console()


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(key): _to_jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(item) for item in obj]
    return obj


def _extract_structured_counts(result) -> Dict[str, int]:
    structured = result.structured_answer.structured
    if structured is None:
        return {
            "supported_claims": 0,
            "unsupported_claims": 0,
            "limitations": 0,
            "conflicts": 0,
        }
    return {
        "supported_claims": len(structured.supported_claims),
        "unsupported_claims": len(structured.unsupported_claims),
        "limitations": len(structured.limitations),
        "conflicts": len(structured.conflicts),
    }


def _render_summary_table(rows: List[Dict[str, object]]) -> None:
    table = Table(show_lines=True, title="Paper-mode validation harness")
    table.add_column("Paper")
    table.add_column("Task")
    table.add_column("Audit")
    table.add_column("Auto")
    table.add_column("Candidates")
    table.add_column("Metrics")
    table.add_column("Supported/Unsupported")
    for row in rows:
        counts = row["counts"]
        auto = row["auto_checks"]
        table.add_row(
            str(row["paper_slug"]),
            str(row["task_type"]),
            str(row["audit_status"]),
            "pass" if auto["passed"] else "fail",
            str(row["candidate_count"]),
            str(row["metric_count"]),
            f"{counts['supported_claims']}/{counts['unsupported_claims']}",
        )
    console.print(table)


def run_harness(*, matrix_path: Path, manifest_path: Path, top_k: int) -> Path:
    manifest_specs = load_manifest(manifest_path)
    matrix_payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    min_papers = int(matrix_payload.get("min_papers", 5))
    matrix_specs = load_validation_matrix(matrix_path)
    validate_matrix_completeness(matrix_specs, min_papers=min_papers)

    service = EvidenceReviewService(top_k=top_k)
    if not service.library:
        console.print("[red]No indexed GenoScribe documents found.[/red]")
        console.print("The full paper benchmark requires a local curated corpus:")
        console.print("  uv run python scripts/corpus_sync.py --download-missing --ingest-missing")
        console.print("")
        console.print("For a public synthetic demo, run:")
        console.print("  uv run python scripts/demo_build_sample_corpus.py")
        console.print(
            "  uv run python scripts/paper_validation_harness.py "
            "--matrix docs/examples/demo_validation_matrix.json "
            "--manifest docs/examples/demo_manifest.json --top-k 4"
        )
        raise SystemExit(2)
    indexed_by_file = map_indexed_doc_ids_by_filename(service.library)

    result_rows: List[Dict[str, object]] = []
    started = time.perf_counter()
    for paper_spec in matrix_specs:
        expected_doc_ids = select_doc_ids_for_slug(
            slug=paper_spec.slug,
            manifest_specs=manifest_specs,
            indexed_doc_ids_by_filename=indexed_by_file,
        )
        if not expected_doc_ids:
            console.print(f"[yellow]Warning:[/yellow] no indexed doc ids found for slug '{paper_spec.slug}'")
        for task in paper_spec.tasks:
            query_result = service.run_query(query=task.query, mode="paper")
            final_doc_ids = [candidate.doc_id for candidate in query_result.candidates]
            counts = _extract_structured_counts(query_result)
            auto_checks = evaluate_auto_checks(
                task_type=task.task_type,
                expected_doc_ids=expected_doc_ids,
                inferred_target_doc_ids=query_result.target_doc_ids,
                final_doc_ids=final_doc_ids,
                audit_status=query_result.structured_answer.audit_status,
                metric_count=len(query_result.metrics),
                supported_claim_count=counts["supported_claims"],
                unsupported_claim_count=counts["unsupported_claims"],
                limitation_count=counts["limitations"],
                conflict_count=counts["conflicts"],
                expected_auto=task.expected_auto,
            )
            manual_template = {
                field_name: ("pending" if field_name != "reviewer_notes" else "")
                for field_name in (task.manual_review_fields or [])
            }
            result_rows.append(
                {
                    "paper_slug": paper_spec.slug,
                    "expected_bucket": paper_spec.expected_bucket,
                    "task_type": task.task_type,
                    "query": task.query,
                    "task_notes": task.notes,
                    "expected_doc_ids": expected_doc_ids,
                    "target_doc_ids": query_result.target_doc_ids,
                    "final_doc_ids": final_doc_ids,
                    "audit_status": query_result.structured_answer.audit_status,
                    "candidate_count": len(query_result.candidates),
                    "metric_count": len(query_result.metrics),
                    "counts": counts,
                    "auto_checks": auto_checks,
                    "manual_review": manual_template,
                    "coverage_notes": list(query_result.bundle_preview.coverage_notes),
                    "verifier_notes": list(query_result.structured_answer.verifier_notes),
                    "timings_ms": dict(query_result.diagnostics.timings_ms),
                    "structured_result": {
                        "bundle_preview": _to_jsonable(query_result.bundle_preview),
                        "metrics": _to_jsonable(query_result.metrics),
                        "structured_answer": _to_jsonable(query_result.structured_answer),
                        "candidates": _to_jsonable(query_result.candidates),
                        "filter_traces": _to_jsonable(query_result.filter_traces),
                    },
                }
            )

    duration_s = time.perf_counter() - started
    summary = summarize_results(result_rows)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "paper",
        "matrix_path": str(matrix_path),
        "manifest_path": str(manifest_path),
        "duration_s": duration_s,
        "summary": summary,
        "results": result_rows,
    }

    out_dir = OUTPUT_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"paper_validation_{_now_stamp()}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _render_summary_table(result_rows)
    console.print(
        "[green]Saved paper-mode validation report:[/green] "
        f"{out_path} | auto pass rate: {summary['auto_passed']}/{summary['total_tasks']}"
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paper-mode validation harness on curated corpus queries.")
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("docs/corpus/paper_validation_matrix.json"),
        help="Validation query matrix JSON.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/corpus/corpus_manifest.json"),
        help="Corpus manifest JSON used to resolve slugs to indexed docs.",
    )
    parser.add_argument("--top-k", type=int, default=4, help="Top-k passages to keep in each review query.")
    args = parser.parse_args()
    run_harness(matrix_path=args.matrix, manifest_path=args.manifest, top_k=args.top_k)


if __name__ == "__main__":
    main()

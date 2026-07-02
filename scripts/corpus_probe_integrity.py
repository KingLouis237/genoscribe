from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from rich.console import Console
from rich.table import Table

from genoscribe.config import OUTPUT_DIR
from genoscribe.corpus import load_manifest

console = Console()


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _is_deictic_query(query: str) -> bool:
    lowered = (query or "").lower()
    return "this " in lowered


def _is_paper_primary_modes(modes: List[str]) -> bool:
    mode_set = {str(mode).strip().lower() for mode in modes}
    return "paper" in mode_set and "assembly" not in mode_set and "variant" not in mode_set


def _latest_probe_report() -> Path:
    report_dir = OUTPUT_DIR / "reports"
    candidates = sorted(report_dir.glob("paper_probe_report_*.json"))
    if not candidates:
        raise FileNotFoundError("No paper_probe_report_*.json artifacts found in outputs/reports.")
    return candidates[-1]


def _render_doc_table(rows: List[Dict[str, object]]) -> None:
    table = Table(show_lines=True, title="Corpus probe integrity")
    table.add_column("Slug")
    table.add_column("Mode intent")
    table.add_column("Indexed doc_type")
    table.add_column("Queries")
    table.add_column("Target inferred")
    table.add_column("Final overlap")
    table.add_column("Integrity")
    for row in rows:
        table.add_row(
            str(row["slug"]),
            str(row["mode_intent"]),
            ",".join(row["indexed_doc_types"]) if row["indexed_doc_types"] else "unknown",
            str(row["query_count"]),
            f"{row['target_inferred_count']}/{row['query_count']}",
            f"{row['final_overlap_count']}/{row['query_count']}",
            "blocked" if row["integrity_blocked"] else "ok",
        )
    console.print(table)


def audit_integrity(
    *,
    manifest_path: Path,
    probe_report_path: Path,
    inventory_path: Path | None = None,
) -> tuple[Path, Path]:
    manifest_specs = load_manifest(manifest_path)
    manifest_map = {spec.slug: spec for spec in manifest_specs}

    probe_payload = json.loads(probe_report_path.read_text(encoding="utf-8"))
    probe_rows = probe_payload.get("rows", [])
    if not isinstance(probe_rows, list) or not probe_rows:
        raise ValueError("Probe report does not contain rows.")

    inventory_payload = None
    if inventory_path:
        inventory_payload = json.loads(inventory_path.read_text(encoding="utf-8"))

    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in probe_rows:
        grouped[str(row.get("slug", ""))].append(row)

    doc_rows: List[Dict[str, object]] = []
    for slug, rows in grouped.items():
        spec = manifest_map.get(slug)
        if spec is None:
            continue
        query_count = len(rows)
        target_inferred_count = sum(1 for row in rows if row.get("target_doc_inferred"))
        final_overlap_count = sum(1 for row in rows if row.get("final_doc_overlap"))
        integrity_reasons = sorted(
            {
                reason
                for row in rows
                for reason in row.get("integrity_reasons", [])
                if str(reason).strip()
            }
        )
        indexed_doc_types = sorted(
            {
                str(doc_type).strip().lower()
                for row in rows
                for doc_type in row.get("indexed_doc_types", [])
                if str(doc_type).strip()
            }
        )
        mode_intent = "paper-primary" if _is_paper_primary_modes(list(spec.modes)) else "mixed/secondary"
        doc_rows.append(
            {
                "slug": slug,
                "title": spec.title,
                "manifest_buckets": list(spec.buckets),
                "manifest_modes": list(spec.modes),
                "mode_intent": mode_intent,
                "expected_doc_type": (spec.expected_doc_type or "").strip().lower() or None,
                "indexed_doc_types": indexed_doc_types,
                "query_count": query_count,
                "target_inferred_count": target_inferred_count,
                "final_overlap_count": final_overlap_count,
                "integrity_blocked": any(bool(row.get("integrity_blocked")) for row in rows),
                "integrity_reasons": integrity_reasons,
            }
        )

    failure_breakdown = {
        "target_inference_failure": sum(1 for row in probe_rows if not row.get("target_doc_inferred")),
        "doc_type_mode_mismatch": sum(
            1
            for row in probe_rows
            if any(
                str(reason).startswith("paper_primary_not_indexed_as_paper")
                or str(reason).startswith("expected_doc_type_mismatch")
                for reason in row.get("integrity_reasons", [])
            )
        ),
        "retrieval_filtering_failure": sum(
            1
            for row in probe_rows
            if row.get("target_doc_inferred") and not row.get("final_doc_overlap")
        ),
        "query_phrasing_issue": sum(
            1
            for row in probe_rows
            if _is_deictic_query(str(row.get("query", ""))) and not row.get("target_doc_inferred")
        ),
        "genuine_evidence_absence": sum(
            1
            for row in probe_rows
            if row.get("audit_status") == "insufficient_evidence" and row.get("final_doc_overlap")
        ),
    }

    explicit_rows = [row for row in probe_rows if not _is_deictic_query(str(row.get("query", "")))]
    deictic_rows = [row for row in probe_rows if _is_deictic_query(str(row.get("query", "")))]
    phrasing_split = {
        "explicit_title": {
            "queries": len(explicit_rows),
            "target_doc_inferred": sum(1 for row in explicit_rows if row.get("target_doc_inferred")),
            "final_doc_overlap": sum(1 for row in explicit_rows if row.get("final_doc_overlap")),
        },
        "deictic": {
            "queries": len(deictic_rows),
            "target_doc_inferred": sum(1 for row in deictic_rows if row.get("target_doc_inferred")),
            "final_doc_overlap": sum(1 for row in deictic_rows if row.get("final_doc_overlap")),
        },
    }

    summary = {
        "total_probe_queries": len(probe_rows),
        "docs_audited": len(doc_rows),
        "integrity_blocked_docs": sum(1 for row in doc_rows if row["integrity_blocked"]),
        "audit_status_counts": dict(Counter(str(row.get("audit_status", "")) for row in probe_rows)),
    }

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "probe_report_path": str(probe_report_path),
        "inventory_path": str(inventory_path) if inventory_path else None,
        "summary": summary,
        "document_consistency": doc_rows,
        "probe_failure_breakdown": failure_breakdown,
        "query_phrasing_split": phrasing_split,
        "inventory_summary": (inventory_payload.get("summary") if inventory_payload else None),
        "inventory_library_stats": (inventory_payload.get("library_stats") if inventory_payload else None),
    }

    out_dir = OUTPUT_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    json_path = out_dir / f"corpus_probe_integrity_{stamp}.json"
    csv_path = out_dir / f"corpus_probe_integrity_{stamp}.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "slug",
                "mode_intent",
                "expected_doc_type",
                "indexed_doc_types",
                "query_count",
                "target_inferred_count",
                "final_overlap_count",
                "integrity_blocked",
                "integrity_reasons",
            ]
        )
        for row in doc_rows:
            writer.writerow(
                [
                    row["slug"],
                    row["mode_intent"],
                    row["expected_doc_type"] or "",
                    ";".join(row["indexed_doc_types"]),
                    row["query_count"],
                    row["target_inferred_count"],
                    row["final_overlap_count"],
                    row["integrity_blocked"],
                    ";".join(row["integrity_reasons"]),
                ]
            )

    _render_doc_table(doc_rows)
    console.print(f"[green]Saved integrity report:[/green] {json_path}")
    console.print(f"[green]Saved integrity CSV:[/green] {csv_path}")
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit corpus probe integrity across manifest intent, indexed doc types, and probe outcomes.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/corpus/corpus_manifest.json"),
        help="Path to corpus manifest.",
    )
    parser.add_argument(
        "--probe-report",
        type=Path,
        default=None,
        help="Path to paper probe report JSON. Defaults to latest paper_probe_report_*.json artifact.",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("src/genomics_assistant_data/outputs/reports/corpus_inventory_20260425_172335.json"),
        help="Optional corpus inventory JSON for context fields in output.",
    )
    args = parser.parse_args()
    probe_report_path = args.probe_report if args.probe_report else _latest_probe_report()
    inventory_path = args.inventory if args.inventory.exists() else None
    audit_integrity(
        manifest_path=args.manifest,
        probe_report_path=probe_report_path,
        inventory_path=inventory_path,
    )


if __name__ == "__main__":
    main()

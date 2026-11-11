from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from genoscribe.eval.oa_benchmark import ALLOWED_BENCHMARK_TRACKS

DEFAULT_BENCHMARK_PATH = Path("docs/benchmarks/oa_benchmark_v1.json")
DEFAULT_MANIFEST_PATH = Path("docs/corpus/oa_benchmark_manifest.json")
DEFAULT_BENCHMARK_TRACK = "core_paper_mode_general"
TASK_TYPES = (
    "scoped_document_query",
    "metric_extraction_query",
    "supported_claim_query",
    "unsupported_topic_query",
    "limitation_conflict_query",
)


@dataclass(frozen=True)
class DraftPaper:
    slug: str
    title: str
    benchmark_track: str = DEFAULT_BENCHMARK_TRACK
    source_url: str = ""


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "oa_paper"


def _validate_declared_track(requested_track: str | None = None) -> str:
    track = requested_track or DEFAULT_BENCHMARK_TRACK
    if track not in ALLOWED_BENCHMARK_TRACKS:
        raise ValueError(f"Invalid benchmark_track: {track}")
    return track


def _load_manifest_papers(path: Path) -> List[DraftPaper]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    papers: List[DraftPaper] = []
    for row in payload.get("documents", []):
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug", "")).strip()
        title = str(row.get("title", "")).strip()
        if not slug or not title:
            continue
        track = _validate_declared_track(
            requested_track=str(row.get("benchmark_track", "")).strip() or None,
        )
        papers.append(
            DraftPaper(
                slug=slug,
                title=title,
                benchmark_track=track,
                source_url=str(row.get("source_url", "")).strip(),
            )
        )
    return papers


def _candidate_question(*, title: str, task_type: str) -> str:
    if task_type == "scoped_document_query":
        return f"In the {title} paper, what is the main study objective and evidence base?"
    if task_type == "metric_extraction_query":
        return f"From the {title} paper, extract explicitly reported benchmark, performance, or cohort metrics."
    if task_type == "supported_claim_query":
        return f"What claim is directly supported by the {title} paper's reported evidence?"
    if task_type == "unsupported_topic_query":
        return f"What clinical or deployment conclusion is not supported by the {title} paper?"
    if task_type == "limitation_conflict_query":
        return f"What limitations, caveats, or conflicting evidence are stated in the {title} paper?"
    raise ValueError(f"Unsupported task_type: {task_type}")


def draft_items_for_paper(paper: DraftPaper) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for task_type in TASK_TYPES:
        item_id = f"{paper.slug}_{task_type}"
        items.append(
            {
                "id": item_id,
                "question": _candidate_question(title=paper.title, task_type=task_type),
                "source_doc": paper.title,
                "source_doc_slug": paper.slug,
                "benchmark_track": paper.benchmark_track,
                "gold_answer": "DRAFT ONLY - not human verified; do not score as gold answer.",
                "expected_audit_state": "TODO_NEEDS_HUMAN_REVIEW",
                "supporting_section_or_page": "TODO: human reviewer must verify section/page.",
                "supporting_quote_or_paraphrase": "TODO: human reviewer must verify supporting text.",
                "candidate_supporting_section": "TODO: optionally add candidate section/page during assisted review.",
                "candidate_supporting_quote_or_paraphrase": "TODO: optionally add candidate quote/paraphrase during assisted review.",
                "unsupported_reason": "TODO: human reviewer must verify if this item is unsupported or limitation-focused.",
                "task_type": task_type,
                "verification_status": "needs_human_review",
                "human_verified_by": "",
                "human_verified_date": "",
                "notes": "Automatically drafted candidate item. Human verification is required before scoring.",
            }
        )
    return items


def _ensure_benchmark_file(path: Path) -> Dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload: Dict[str, Any] = {
        "schema_version": 1,
        "benchmark_name": "oa_benchmark_v1",
        "description": "Public open-access paper-mode benchmark draft file. Items are not scoring-ready until verification_status is human_verified.",
        "gold_answer_policy": "manual_human_verified_only",
        "items": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def append_draft_items(*, benchmark_path: Path, papers: Iterable[DraftPaper]) -> int:
    payload = _ensure_benchmark_file(benchmark_path)
    items = payload.setdefault("items", [])
    if not isinstance(items, list):
        raise ValueError("Benchmark file must contain an items list.")

    existing_ids = {str(item.get("id", "")) for item in items if isinstance(item, dict)}
    added = 0
    for paper in papers:
        for item in draft_items_for_paper(paper):
            if item["id"] in existing_ids:
                continue
            items.append(item)
            existing_ids.add(item["id"])
            added += 1

    benchmark_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return added


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft non-scoring OA benchmark candidate items for human review.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK_PATH)
    parser.add_argument("--paper-title", default="", help="Manual paper title when not using manifest entries.")
    parser.add_argument("--paper-slug", default="", help="Manual paper slug when not using manifest entries.")
    parser.add_argument("--source-url", default="", help="Optional source URL for manual paper metadata.")
    parser.add_argument(
        "--benchmark-track",
        default="core_paper_mode_general",
        choices=tuple(sorted(ALLOWED_BENCHMARK_TRACKS)),
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    papers: List[DraftPaper] = []
    if args.paper_title:
        slug = args.paper_slug.strip() or _slugify(args.paper_title)
        track = _validate_declared_track(args.benchmark_track)
        papers.append(
            DraftPaper(slug=slug, title=args.paper_title.strip(), benchmark_track=track, source_url=args.source_url)
        )
    else:
        papers = _load_manifest_papers(args.manifest)

    added = append_draft_items(benchmark_path=args.benchmark, papers=papers)
    print(f"Draft papers processed: {len(papers)}")
    print(f"Draft benchmark items added: {added}")
    print("All drafted items have verification_status='needs_human_review' and must not be scored as gold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

REQUIRED_ITEM_FIELDS = (
    "id",
    "question",
    "source_doc",
    "source_doc_slug",
    "benchmark_track",
    "gold_answer",
    "expected_audit_state",
    "supporting_section_or_page",
    "supporting_quote_or_paraphrase",
    "candidate_supporting_section",
    "candidate_supporting_quote_or_paraphrase",
    "unsupported_reason",
    "task_type",
    "verification_status",
    "human_verified_by",
    "human_verified_date",
    "notes",
)

ALLOWED_AUDIT_STATES = {
    "supported",
    "partially_supported",
    "insufficient_evidence",
    "conflicting_evidence",
    "off_target_evidence",
}

ALLOWED_BENCHMARK_TRACKS = {
    "core_paper_mode_general",
    "assembly_qc_specialized",
}

ALLOWED_TASK_TYPES = {
    "scoped_document_query",
    "metric_extraction_query",
    "supported_claim_query",
    "unsupported_topic_query",
    "limitation_conflict_query",
}

ALLOWED_VERIFICATION_STATUSES = {
    "needs_human_review",
    "human_verified",
}


@dataclass(frozen=True)
class OABenchmarkItem:
    id: str
    question: str
    source_doc: str
    source_doc_slug: str
    benchmark_track: str
    gold_answer: str
    expected_audit_state: str
    supporting_section_or_page: str
    supporting_quote_or_paraphrase: str
    candidate_supporting_section: str
    candidate_supporting_quote_or_paraphrase: str
    unsupported_reason: str
    task_type: str
    verification_status: str
    human_verified_by: str
    human_verified_date: str
    notes: str


@dataclass(frozen=True)
class OABenchmark:
    schema_version: int
    benchmark_name: str
    description: str
    gold_answer_policy: str
    items: List[OABenchmarkItem]


def _is_todo(value: str) -> bool:
    stripped = value.strip().lower()
    return not stripped or stripped.startswith("todo")


def _validate_enum(*, value: str, allowed: Iterable[str], field: str, item_id: str) -> None:
    if value not in set(allowed):
        raise ValueError(f"Invalid {field} for {item_id}: {value}")


def _validate_enum_or_todo(*, value: str, allowed: Iterable[str], field: str, item_id: str) -> None:
    if _is_todo(value):
        return
    _validate_enum(value=value, allowed=allowed, field=field, item_id=item_id)


def load_oa_benchmark(path: Path) -> OABenchmark:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items_payload = payload.get("items")
    if not isinstance(items_payload, list):
        raise ValueError("OA benchmark file must contain an 'items' list.")

    items: List[OABenchmarkItem] = []
    seen_ids: set[str] = set()
    for row in items_payload:
        if not isinstance(row, dict):
            raise ValueError("Each OA benchmark item must be an object.")
        missing = [field for field in REQUIRED_ITEM_FIELDS if field not in row]
        if missing:
            raise ValueError(f"OA benchmark item is missing required fields: {missing}")

        values = {field: str(row[field]).strip() for field in REQUIRED_ITEM_FIELDS}
        item_id = values["id"]
        if item_id in seen_ids:
            raise ValueError(f"Duplicate OA benchmark item id: {item_id}")
        seen_ids.add(item_id)

        _validate_enum_or_todo(
            value=values["expected_audit_state"],
            allowed=ALLOWED_AUDIT_STATES,
            field="expected_audit_state",
            item_id=item_id,
        )
        _validate_enum(
            value=values["benchmark_track"],
            allowed=ALLOWED_BENCHMARK_TRACKS,
            field="benchmark_track",
            item_id=item_id,
        )
        _validate_enum_or_todo(
            value=values["task_type"],
            allowed=ALLOWED_TASK_TYPES,
            field="task_type",
            item_id=item_id,
        )
        _validate_enum_or_todo(
            value=values["verification_status"],
            allowed=ALLOWED_VERIFICATION_STATUSES,
            field="verification_status",
            item_id=item_id,
        )

        items.append(OABenchmarkItem(**values))

    return OABenchmark(
        schema_version=int(payload.get("schema_version", 1)),
        benchmark_name=str(payload.get("benchmark_name", "")).strip(),
        description=str(payload.get("description", "")).strip(),
        gold_answer_policy=str(payload.get("gold_answer_policy", "")).strip(),
        items=items,
    )


def validate_scoring_ready(benchmark: OABenchmark) -> None:
    """Reject draft benchmark items before any future scorer treats them as gold."""
    not_verified = [item.id for item in benchmark.items if item.verification_status != "human_verified"]
    if not_verified:
        raise ValueError(f"OA benchmark contains non-human-verified items: {not_verified}")

    incomplete = [
        item.id
        for item in benchmark.items
        if _is_todo(item.gold_answer)
        or _is_todo(item.expected_audit_state)
        or _is_todo(item.supporting_section_or_page)
        or _is_todo(item.supporting_quote_or_paraphrase)
        or not item.human_verified_by.strip()
        or not item.human_verified_date.strip()
    ]
    if incomplete:
        raise ValueError(f"OA benchmark contains incomplete human-verified items: {incomplete}")

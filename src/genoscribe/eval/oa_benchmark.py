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
    "gold_answer",
    "expected_audit_state",
    "supporting_section_or_page",
    "supporting_quote_or_paraphrase",
    "unsupported_reason",
    "task_type",
    "notes",
)

ALLOWED_AUDIT_STATES = {
    "supported",
    "partially_supported",
    "insufficient_evidence",
    "conflicting_evidence",
    "off_target_evidence",
}

ALLOWED_TASK_TYPES = {
    "scoped_document_query",
    "metric_extraction_query",
    "supported_claim_query",
    "unsupported_topic_query",
    "limitation_conflict_query",
}


@dataclass(frozen=True)
class OABenchmarkItem:
    id: str
    question: str
    source_doc: str
    source_doc_slug: str
    gold_answer: str
    expected_audit_state: str
    supporting_section_or_page: str
    supporting_quote_or_paraphrase: str
    unsupported_reason: str
    task_type: str
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


def _validate_enum_or_todo(*, value: str, allowed: Iterable[str], field: str, item_id: str) -> None:
    if _is_todo(value):
        return
    if value not in set(allowed):
        raise ValueError(f"Invalid {field} for {item_id}: {value}")


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
        _validate_enum_or_todo(
            value=values["task_type"],
            allowed=ALLOWED_TASK_TYPES,
            field="task_type",
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

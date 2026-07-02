from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from genoscribe.corpus import CorpusDocumentSpec

REQUIRED_TASK_TYPES = (
    "scoped_document_query",
    "metric_extraction_query",
    "supported_claim_query",
    "unsupported_topic_query",
    "limitation_conflict_query",
)


@dataclass(frozen=True)
class PaperValidationTask:
    task_type: str
    query: str
    notes: str = ""
    expected_auto: Dict[str, object] = field(default_factory=dict)
    manual_review_fields: Sequence[str] = field(
        default_factory=lambda: (
            "citation_faithfulness",
            "scientific_soundness",
            "uncertainty_handling",
            "reviewer_notes",
        )
    )


@dataclass(frozen=True)
class PaperValidationSpec:
    slug: str
    expected_bucket: str
    tasks: Sequence[PaperValidationTask]
    notes: str = ""


def load_validation_matrix(path: Path) -> List[PaperValidationSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    papers = payload.get("papers")
    if not isinstance(papers, list) or not papers:
        raise ValueError("Validation matrix must define a non-empty 'papers' list.")
    specs: List[PaperValidationSpec] = []
    for item in papers:
        if not isinstance(item, dict):
            raise ValueError("Each paper entry must be an object.")
        slug = str(item.get("slug", "")).strip()
        expected_bucket = str(item.get("expected_bucket", "")).strip()
        if not slug or not expected_bucket:
            raise ValueError(f"Paper entry missing slug/expected_bucket: {item}")
        raw_tasks = item.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise ValueError(f"Paper '{slug}' must define a non-empty tasks list.")
        tasks: List[PaperValidationTask] = []
        for task in raw_tasks:
            if not isinstance(task, dict):
                raise ValueError(f"Paper '{slug}' contains invalid task entry: {task}")
            task_type = str(task.get("task_type", "")).strip()
            query = str(task.get("query", "")).strip()
            if not task_type or not query:
                raise ValueError(f"Paper '{slug}' task missing task_type/query: {task}")
            if task_type not in REQUIRED_TASK_TYPES:
                raise ValueError(f"Paper '{slug}' has unsupported task_type '{task_type}'.")
            manual_fields = task.get("manual_review_fields")
            if manual_fields:
                manual_fields_value = tuple(str(field).strip() for field in manual_fields if str(field).strip())
            else:
                manual_fields_value = (
                    "citation_faithfulness",
                    "scientific_soundness",
                    "uncertainty_handling",
                    "reviewer_notes",
                )
            tasks.append(
                PaperValidationTask(
                    task_type=task_type,
                    query=query,
                    notes=str(task.get("notes", "")).strip(),
                    expected_auto=dict(task.get("expected_auto") or {}),
                    manual_review_fields=manual_fields_value,
                )
            )
        specs.append(
            PaperValidationSpec(
                slug=slug,
                expected_bucket=expected_bucket,
                tasks=tuple(tasks),
                notes=str(item.get("notes", "")).strip(),
            )
        )
    return specs


def validate_matrix_completeness(specs: Sequence[PaperValidationSpec], *, min_papers: int = 5) -> None:
    if len(specs) < min_papers:
        raise ValueError(f"Validation matrix should contain at least {min_papers} papers.")
    for spec in specs:
        seen = {task.task_type for task in spec.tasks}
        missing = [task_type for task_type in REQUIRED_TASK_TYPES if task_type not in seen]
        if missing:
            raise ValueError(f"Paper '{spec.slug}' is missing required task types: {missing}")


def select_doc_ids_for_slug(
    *,
    slug: str,
    manifest_specs: Sequence[CorpusDocumentSpec],
    indexed_doc_ids_by_filename: Dict[str, List[str]],
) -> List[str]:
    manifest_map = {spec.slug: spec for spec in manifest_specs}
    spec = manifest_map.get(slug)
    if not spec:
        raise ValueError(f"Validation slug '{slug}' was not found in corpus manifest.")
    return list(indexed_doc_ids_by_filename.get(spec.filename, []))


def evaluate_auto_checks(
    *,
    task_type: str,
    expected_doc_ids: Sequence[str],
    inferred_target_doc_ids: Sequence[str],
    final_doc_ids: Sequence[str],
    audit_status: str,
    metric_count: int,
    supported_claim_count: int,
    unsupported_claim_count: int,
    limitation_count: int,
    conflict_count: int,
    expected_auto: Dict[str, object] | None = None,
) -> Dict[str, object]:
    expected_auto = expected_auto or {}
    expected_set = set(expected_doc_ids)
    inferred_set = set(inferred_target_doc_ids)
    final_set = set(final_doc_ids)
    target_inferred = bool(expected_set & inferred_set) if expected_set else False
    final_overlap = bool(expected_set & final_set) if expected_set else False
    metric_min = int(expected_auto.get("metric_min", 1))

    checks: Dict[str, bool] = {
        "target_doc_inferred": target_inferred,
        "final_doc_overlap": final_overlap,
    }

    if task_type == "scoped_document_query":
        checks["non_off_target_audit"] = audit_status != "off_target_evidence"
    elif task_type == "metric_extraction_query":
        checks["metric_minimum_met"] = metric_count >= metric_min
        checks["non_off_target_audit"] = audit_status != "off_target_evidence"
    elif task_type == "supported_claim_query":
        checks["supported_claim_present"] = supported_claim_count > 0
        checks["non_insufficient_audit"] = audit_status in {"supported", "partially_supported", "conflicting_evidence"}
    elif task_type == "unsupported_topic_query":
        checks["unsupported_flagged"] = unsupported_claim_count > 0 or audit_status in {
            "insufficient_evidence",
            "off_target_evidence",
        }
    elif task_type == "limitation_conflict_query":
        checks["limitation_or_conflict_present"] = (limitation_count + conflict_count) > 0
    else:
        raise ValueError(f"Unsupported task_type: {task_type}")

    passed = all(checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "task_type": task_type,
        "audit_status": audit_status,
    }


def summarize_results(rows: Iterable[Dict[str, object]]) -> Dict[str, object]:
    rows_list = list(rows)
    total = len(rows_list)
    passed = sum(1 for row in rows_list if row.get("auto_checks", {}).get("passed"))
    by_task: Dict[str, Dict[str, int]] = {}
    for row in rows_list:
        task_type = str(row.get("task_type"))
        stats = by_task.setdefault(task_type, {"total": 0, "passed": 0})
        stats["total"] += 1
        if row.get("auto_checks", {}).get("passed"):
            stats["passed"] += 1
    return {
        "total_tasks": total,
        "auto_passed": passed,
        "auto_failed": total - passed,
        "auto_pass_rate": (passed / total) if total else 0.0,
        "by_task_type": by_task,
    }


__all__ = [
    "REQUIRED_TASK_TYPES",
    "PaperValidationTask",
    "PaperValidationSpec",
    "load_validation_matrix",
    "validate_matrix_completeness",
    "select_doc_ids_for_slug",
    "evaluate_auto_checks",
    "summarize_results",
]

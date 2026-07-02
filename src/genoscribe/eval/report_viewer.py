from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Mapping, Sequence

ReportKind = Literal["probe", "validation"]

FAIL_AUDIT_STATUSES = {"off_target_evidence", "insufficient_evidence"}


@dataclass(frozen=True)
class ReportSummary:
    kind: ReportKind
    total: int
    pass_rate: float | None
    target_doc_inferred_count: int
    final_doc_overlap_count: int
    target_doc_inferred_rate: float
    final_doc_overlap_rate: float
    audit_status_counts: Dict[str, int]


def detect_report_kind(payload: Mapping[str, Any]) -> ReportKind:
    if isinstance(payload.get("rows"), list):
        return "probe"
    if isinstance(payload.get("results"), list):
        return "validation"
    raise ValueError("Unsupported report format: expected probe rows or validation results.")


def get_rows(payload: Mapping[str, Any]) -> tuple[ReportKind, List[Mapping[str, Any]]]:
    kind = detect_report_kind(payload)
    rows = payload.get("rows") if kind == "probe" else payload.get("results")
    if not isinstance(rows, list):
        return kind, []
    return kind, [row for row in rows if isinstance(row, Mapping)]


def _safe_div(num: int, den: int) -> float:
    return float(num) / float(den) if den else 0.0


def _row_target_doc_inferred(kind: ReportKind, row: Mapping[str, Any]) -> bool:
    if kind == "probe":
        return bool(row.get("target_doc_inferred"))
    checks = row.get("auto_checks", {}).get("checks", {})
    if isinstance(checks, Mapping) and "target_doc_inferred" in checks:
        return bool(checks.get("target_doc_inferred"))
    return bool(row.get("target_doc_ids"))


def _row_final_doc_overlap(kind: ReportKind, row: Mapping[str, Any]) -> bool:
    if kind == "probe":
        return bool(row.get("final_doc_overlap"))
    checks = row.get("auto_checks", {}).get("checks", {})
    if isinstance(checks, Mapping) and "final_doc_overlap" in checks:
        return bool(checks.get("final_doc_overlap"))
    expected = set(row.get("expected_doc_ids") or [])
    final = set(row.get("final_doc_ids") or [])
    return bool(expected & final)


def summarize_report(payload: Mapping[str, Any]) -> ReportSummary:
    kind, rows = get_rows(payload)
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), Mapping) else {}
    total = int(summary.get("total_queries" if kind == "probe" else "total_tasks", len(rows)))
    if total <= 0:
        total = len(rows)
    target_doc_inferred_count = sum(1 for row in rows if _row_target_doc_inferred(kind, row))
    final_doc_overlap_count = sum(1 for row in rows if _row_final_doc_overlap(kind, row))
    audit_status_counts = dict(Counter(str(row.get("audit_status", "unknown")) for row in rows))
    pass_rate: float | None
    if kind == "validation":
        raw = summary.get("auto_pass_rate")
        pass_rate = float(raw) if isinstance(raw, (int, float)) else _safe_div(
            int(summary.get("auto_passed", 0)),
            int(summary.get("total_tasks", total)),
        )
    else:
        pass_rate = None
    return ReportSummary(
        kind=kind,
        total=total,
        pass_rate=pass_rate,
        target_doc_inferred_count=target_doc_inferred_count,
        final_doc_overlap_count=final_doc_overlap_count,
        target_doc_inferred_rate=_safe_div(target_doc_inferred_count, total),
        final_doc_overlap_rate=_safe_div(final_doc_overlap_count, total),
        audit_status_counts=audit_status_counts,
    )


def row_key(kind: ReportKind, row: Mapping[str, Any]) -> str:
    if kind == "probe":
        return f"{row.get('slug', 'unknown')}::{row.get('query_id', 'query')}"
    return f"{row.get('paper_slug', 'unknown')}::{row.get('task_type', 'task')}"


def row_is_failure(kind: ReportKind, row: Mapping[str, Any]) -> bool:
    if kind == "validation":
        checks = row.get("auto_checks", {})
        if isinstance(checks, Mapping):
            if "passed" in checks:
                return not bool(checks.get("passed"))
            check_map = checks.get("checks", {})
            if isinstance(check_map, Mapping):
                return any(not bool(value) for value in check_map.values())
        return False
    # probe
    if not _row_target_doc_inferred(kind, row):
        return True
    if not _row_final_doc_overlap(kind, row):
        return True
    return str(row.get("audit_status", "")) in FAIL_AUDIT_STATUSES


def failed_rows(payload: Mapping[str, Any]) -> tuple[ReportKind, List[Mapping[str, Any]]]:
    kind, rows = get_rows(payload)
    return kind, [row for row in rows if row_is_failure(kind, row)]


def failed_check_counts(kind: ReportKind, rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    if kind == "validation":
        for row in rows:
            checks = row.get("auto_checks", {}).get("checks", {})
            if not isinstance(checks, Mapping):
                continue
            for key, value in checks.items():
                if not bool(value):
                    counts[str(key)] += 1
        return dict(counts)

    for row in rows:
        if not bool(row.get("target_doc_inferred")):
            counts["target_doc_inferred"] += 1
        if not bool(row.get("final_doc_overlap")):
            counts["final_doc_overlap"] += 1
        status = str(row.get("audit_status", ""))
        if status == "off_target_evidence":
            counts["off_target_audit"] += 1
        if status == "insufficient_evidence":
            counts["insufficient_evidence_audit"] += 1
    return dict(counts)


def failure_breakdown(payload: Mapping[str, Any]) -> Dict[str, Dict[str, int]]:
    kind, rows = failed_rows(payload)
    by_document = Counter(
        str(row.get("slug") if kind == "probe" else row.get("paper_slug", "unknown")) for row in rows
    )
    by_task = Counter(str(row.get("task_type", "unknown")) for row in rows)
    by_audit = Counter(str(row.get("audit_status", "unknown")) for row in rows)
    return {
        "by_document": dict(by_document),
        "by_task_type": dict(by_task),
        "by_failed_check": failed_check_counts(kind, rows),
        "by_audit_status": dict(by_audit),
    }


def compare_reports(base_payload: Mapping[str, Any], candidate_payload: Mapping[str, Any]) -> Dict[str, Any]:
    base_kind, base_rows = get_rows(base_payload)
    cand_kind, cand_rows = get_rows(candidate_payload)
    if base_kind != cand_kind:
        raise ValueError("Cannot compare different report kinds.")

    base_map = {row_key(base_kind, row): row for row in base_rows}
    cand_map = {row_key(cand_kind, row): row for row in cand_rows}
    common_keys = sorted(set(base_map) & set(cand_map))
    fixed: List[str] = []
    regressed: List[str] = []
    unchanged_fail: List[str] = []
    for key in common_keys:
        base_fail = row_is_failure(base_kind, base_map[key])
        cand_fail = row_is_failure(cand_kind, cand_map[key])
        if base_fail and not cand_fail:
            fixed.append(key)
        elif (not base_fail) and cand_fail:
            regressed.append(key)
        elif base_fail and cand_fail:
            unchanged_fail.append(key)
    return {
        "kind": base_kind,
        "common_rows": len(common_keys),
        "fixed": fixed,
        "regressed": regressed,
        "unchanged_fail": unchanged_fail,
    }


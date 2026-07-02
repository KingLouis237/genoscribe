from __future__ import annotations

from genoscribe.eval.report_viewer import (
    compare_reports,
    failure_breakdown,
    summarize_report,
)


def test_summarize_probe_report() -> None:
    payload = {
        "summary": {"total_queries": 3},
        "rows": [
            {"slug": "a", "query_id": "q1", "target_doc_inferred": True, "final_doc_overlap": True, "audit_status": "supported"},
            {
                "slug": "a",
                "query_id": "q2",
                "target_doc_inferred": False,
                "final_doc_overlap": False,
                "audit_status": "off_target_evidence",
            },
            {
                "slug": "b",
                "query_id": "q3",
                "target_doc_inferred": True,
                "final_doc_overlap": True,
                "audit_status": "insufficient_evidence",
            },
        ],
    }
    summary = summarize_report(payload)
    assert summary.kind == "probe"
    assert summary.total == 3
    assert summary.pass_rate is None
    assert summary.target_doc_inferred_count == 2
    assert summary.final_doc_overlap_count == 2
    assert summary.audit_status_counts["off_target_evidence"] == 1


def test_summarize_validation_report_and_breakdowns() -> None:
    payload = {
        "summary": {"total_tasks": 2, "auto_pass_rate": 0.5},
        "results": [
            {
                "paper_slug": "doc1",
                "task_type": "scoped_document_query",
                "audit_status": "supported",
                "auto_checks": {
                    "passed": True,
                    "checks": {"target_doc_inferred": True, "final_doc_overlap": True},
                },
            },
            {
                "paper_slug": "doc2",
                "task_type": "metric_query",
                "audit_status": "off_target_evidence",
                "auto_checks": {
                    "passed": False,
                    "checks": {"target_doc_inferred": False, "final_doc_overlap": False},
                },
            },
        ],
    }
    summary = summarize_report(payload)
    assert summary.kind == "validation"
    assert summary.pass_rate == 0.5
    breakdown = failure_breakdown(payload)
    assert breakdown["by_document"]["doc2"] == 1
    assert breakdown["by_task_type"]["metric_query"] == 1
    assert breakdown["by_failed_check"]["target_doc_inferred"] == 1


def test_compare_reports_fixed_and_regressed() -> None:
    base = {
        "rows": [
            {
                "slug": "doc",
                "query_id": "q1",
                "target_doc_inferred": False,
                "final_doc_overlap": False,
                "audit_status": "off_target_evidence",
            },
            {
                "slug": "doc",
                "query_id": "q2",
                "target_doc_inferred": True,
                "final_doc_overlap": True,
                "audit_status": "supported",
            },
        ]
    }
    cand = {
        "rows": [
            {
                "slug": "doc",
                "query_id": "q1",
                "target_doc_inferred": True,
                "final_doc_overlap": True,
                "audit_status": "supported",
            },
            {
                "slug": "doc",
                "query_id": "q2",
                "target_doc_inferred": False,
                "final_doc_overlap": False,
                "audit_status": "off_target_evidence",
            },
        ]
    }
    delta = compare_reports(base, cand)
    assert "doc::q1" in delta["fixed"]
    assert "doc::q2" in delta["regressed"]

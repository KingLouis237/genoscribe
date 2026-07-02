from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

from genoscribe.corpus import CorpusDocumentSpec
from genoscribe.eval.paper_validation import (
    evaluate_auto_checks,
    load_validation_matrix,
    select_doc_ids_for_slug,
    summarize_results,
    validate_matrix_completeness,
)


def test_load_validation_matrix_and_completeness(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    base_tasks = [
        {"task_type": "scoped_document_query", "query": "q1"},
        {"task_type": "metric_extraction_query", "query": "q2"},
        {"task_type": "supported_claim_query", "query": "q3"},
        {"task_type": "unsupported_topic_query", "query": "q4"},
        {"task_type": "limitation_conflict_query", "query": "q5"},
    ]
    matrix.write_text(
        json.dumps(
            {
                "papers": [
                    {"slug": f"paper-{idx}", "expected_bucket": "core_benchmark", "tasks": base_tasks}
                    for idx in range(5)
                ]
            }
        ),
        encoding="utf-8",
    )
    specs = load_validation_matrix(matrix)
    validate_matrix_completeness(specs)
    assert len(specs) == 5


def test_validate_matrix_completeness_requires_all_task_types(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "slug": f"paper-{idx}",
                        "expected_bucket": "core_benchmark",
                        "tasks": [{"task_type": "scoped_document_query", "query": "q1"}],
                    }
                    for idx in range(5)
                ]
            }
        ),
        encoding="utf-8",
    )
    specs = load_validation_matrix(matrix)
    with pytest.raises(ValueError, match="missing required task types"):
        validate_matrix_completeness(specs)


def test_select_doc_ids_for_slug_resolves_manifest_filename() -> None:
    manifest_specs = [
        CorpusDocumentSpec(
            slug="alpha",
            title="Alpha",
            filename="alpha.pdf",
            buckets=("core_benchmark",),
            modes=("paper",),
        )
    ]
    indexed = {"alpha.pdf": ["alpha-doc-1"]}
    doc_ids = select_doc_ids_for_slug(slug="alpha", manifest_specs=manifest_specs, indexed_doc_ids_by_filename=indexed)
    assert doc_ids == ["alpha-doc-1"]


def test_evaluate_auto_checks_and_summary() -> None:
    scoped = evaluate_auto_checks(
        task_type="scoped_document_query",
        expected_doc_ids=["doc-a"],
        inferred_target_doc_ids=["doc-a"],
        final_doc_ids=["doc-a"],
        audit_status="supported",
        metric_count=0,
        supported_claim_count=1,
        unsupported_claim_count=0,
        limitation_count=1,
        conflict_count=0,
    )
    unsupported = evaluate_auto_checks(
        task_type="unsupported_topic_query",
        expected_doc_ids=["doc-a"],
        inferred_target_doc_ids=["doc-a"],
        final_doc_ids=["doc-a"],
        audit_status="insufficient_evidence",
        metric_count=0,
        supported_claim_count=0,
        unsupported_claim_count=0,
        limitation_count=0,
        conflict_count=0,
    )
    summary = summarize_results(
        [
            {"task_type": "scoped_document_query", "auto_checks": scoped},
            {"task_type": "unsupported_topic_query", "auto_checks": unsupported},
        ]
    )
    assert scoped["passed"] is True
    assert unsupported["passed"] is True
    assert summary["auto_passed"] == 2


def test_harness_exits_cleanly_when_library_is_empty(tmp_path: Path, monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("paper_validation_harness", "scripts/paper_validation_harness.py")
    assert spec and spec.loader
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    matrix = tmp_path / "matrix.json"
    manifest = tmp_path / "manifest.json"
    matrix.write_text(
        json.dumps(
            {
                "min_papers": 1,
                "papers": [
                    {
                        "slug": "demo",
                        "expected_bucket": "generalization",
                        "tasks": [
                            {"task_type": "scoped_document_query", "query": "q1"},
                            {"task_type": "metric_extraction_query", "query": "q2"},
                            {"task_type": "supported_claim_query", "query": "q3"},
                            {"task_type": "unsupported_topic_query", "query": "q4"},
                            {"task_type": "limitation_conflict_query", "query": "q5"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text('{"documents": []}', encoding="utf-8")

    class EmptyService:
        library = []

        def __init__(self, top_k: int = 4) -> None:
            self.top_k = top_k

    monkeypatch.setattr(harness, "EvidenceReviewService", EmptyService)
    monkeypatch.setattr(harness, "load_manifest", lambda path: [])

    with pytest.raises(SystemExit) as exc:
        harness.run_harness(matrix_path=matrix, manifest_path=manifest, top_k=4)

    assert exc.value.code == 2

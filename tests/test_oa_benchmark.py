from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from genoscribe.corpus import load_manifest
from genoscribe.eval.oa_benchmark import REQUIRED_ITEM_FIELDS, load_oa_benchmark, validate_scoring_ready


def _valid_item(**overrides: str) -> dict[str, str]:
    item = {
        "id": "item_1",
        "question": "What does the paper show?",
        "source_doc": "An open access genomics paper",
        "source_doc_slug": "oa_genomics_paper",
        "benchmark_track": "core_paper_mode_general",
        "gold_answer": "Human-verified answer.",
        "expected_audit_state": "supported",
        "supporting_section_or_page": "Results, page 4",
        "supporting_quote_or_paraphrase": "The paper reports the supported result.",
        "candidate_supporting_section": "Results",
        "candidate_supporting_quote_or_paraphrase": "Candidate draft support.",
        "unsupported_reason": "",
        "task_type": "supported_claim_query",
        "verification_status": "human_verified",
        "human_verified_by": "reviewer-a",
        "human_verified_date": "2026-08-11",
        "notes": "Verified test fixture.",
    }
    item.update(overrides)
    return item


def test_oa_benchmark_template_loads() -> None:
    benchmark = load_oa_benchmark(Path("docs/benchmarks/oa_benchmark_v1.template.json"))

    assert benchmark.schema_version == 1
    assert benchmark.benchmark_name == "oa_benchmark_v1"
    assert benchmark.gold_answer_policy == "manual_human_verified_only"
    assert len(benchmark.items) == 1
    assert benchmark.items[0].verification_status == "needs_human_review"
    assert benchmark.items[0].gold_answer.lower().startswith("todo")


def test_oa_benchmark_v1_file_loads_empty_or_draft() -> None:
    benchmark = load_oa_benchmark(Path("docs/benchmarks/oa_benchmark_v1.json"))

    assert benchmark.benchmark_name == "oa_benchmark_v1"
    assert all(item.verification_status in {"needs_human_review", "human_verified"} for item in benchmark.items)


def test_oa_benchmark_template_contains_required_item_fields() -> None:
    payload = json.loads(Path("docs/benchmarks/oa_benchmark_v1.template.json").read_text(encoding="utf-8"))
    item = payload["items"][0]

    assert set(REQUIRED_ITEM_FIELDS).issubset(item)


def test_oa_benchmark_loader_rejects_missing_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad_oa_benchmark.json"
    path.write_text(json.dumps({"items": [{"id": "bad"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required fields"):
        load_oa_benchmark(path)


def test_needs_human_review_items_load_but_are_not_scoring_ready(tmp_path: Path) -> None:
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps({"items": [_valid_item(verification_status="needs_human_review", gold_answer="DRAFT ONLY")]}),
        encoding="utf-8",
    )

    benchmark = load_oa_benchmark(path)
    assert benchmark.items[0].verification_status == "needs_human_review"
    with pytest.raises(ValueError, match="non-human-verified"):
        validate_scoring_ready(benchmark)


def test_human_verified_items_load_and_can_be_scoring_ready(tmp_path: Path) -> None:
    path = tmp_path / "verified.json"
    path.write_text(json.dumps({"items": [_valid_item()]}), encoding="utf-8")

    benchmark = load_oa_benchmark(path)
    validate_scoring_ready(benchmark)
    assert benchmark.items[0].verification_status == "human_verified"


def test_invalid_verification_status_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"items": [_valid_item(verification_status="model_generated")]}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid verification_status"):
        load_oa_benchmark(path)


def test_genomeqc_and_solorina_must_use_assembly_track(tmp_path: Path) -> None:
    path = tmp_path / "bad_track.json"
    path.write_text(
        json.dumps(
            {
                "items": [
                    _valid_item(
                        id="genomeqc_bad_track",
                        source_doc="GenomeQC assembly quality paper",
                        source_doc_slug="genomeqc_quality",
                        benchmark_track="core_paper_mode_general",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="assembly_qc_specialized"):
        load_oa_benchmark(path)


def test_oa_benchmark_manifest_template_loads_empty() -> None:
    specs = load_manifest(Path("docs/corpus/oa_benchmark_manifest.json"))

    assert specs == []


def test_draft_script_adds_five_non_scoring_items(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("draft_oa_benchmark_items", "scripts/draft_oa_benchmark_items.py")
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = script
    spec.loader.exec_module(script)

    benchmark_path = tmp_path / "oa_benchmark_v1.json"
    paper = script.DraftPaper(slug="test_oa_paper", title="Test OA Genomics Paper")
    added = script.append_draft_items(benchmark_path=benchmark_path, papers=[paper])

    benchmark = load_oa_benchmark(benchmark_path)
    assert added == 5
    assert len(benchmark.items) == 5
    assert {item.task_type for item in benchmark.items} == set(script.TASK_TYPES)
    assert {item.verification_status for item in benchmark.items} == {"needs_human_review"}
    with pytest.raises(ValueError, match="non-human-verified"):
        validate_scoring_ready(benchmark)

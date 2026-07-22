from __future__ import annotations

import json
from pathlib import Path

import pytest

from genoscribe.corpus import load_manifest
from genoscribe.eval.oa_benchmark import REQUIRED_ITEM_FIELDS, load_oa_benchmark


def test_oa_benchmark_template_loads() -> None:
    benchmark = load_oa_benchmark(Path("docs/benchmarks/oa_benchmark_v1.template.json"))

    assert benchmark.schema_version == 1
    assert benchmark.benchmark_name == "oa_benchmark_v1"
    assert benchmark.gold_answer_policy == "manual_human_verified_only"
    assert len(benchmark.items) == 1
    assert benchmark.items[0].gold_answer.lower().startswith("todo")


def test_oa_benchmark_template_contains_required_item_fields() -> None:
    payload = json.loads(Path("docs/benchmarks/oa_benchmark_v1.template.json").read_text(encoding="utf-8"))
    item = payload["items"][0]

    assert set(REQUIRED_ITEM_FIELDS).issubset(item)


def test_oa_benchmark_loader_rejects_missing_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad_oa_benchmark.json"
    path.write_text(json.dumps({"items": [{"id": "bad"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required fields"):
        load_oa_benchmark(path)


def test_oa_benchmark_manifest_template_loads_empty() -> None:
    specs = load_manifest(Path("docs/corpus/oa_benchmark_manifest.json"))

    assert specs == []

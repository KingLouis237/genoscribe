from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from genoscribe.corpus import load_manifest
from genoscribe.eval.paper_validation import load_validation_matrix, validate_matrix_completeness


def test_demo_paper_exists_and_is_synthetic() -> None:
    path = Path("docs/examples/demo_paper.md")
    text = path.read_text(encoding="utf-8")

    assert path.exists()
    assert "GenoScribe-Scout" in text
    assert "AUROC" in text
    assert "AUPRC" in text
    assert "not a clinical tool" in text


def test_demo_manifest_loads() -> None:
    specs = load_manifest(Path("docs/examples/demo_manifest.json"))

    assert len(specs) == 1
    assert specs[0].slug == "genoscribe_scout_demo"
    assert specs[0].filename == "genoscribe_demo_paper.md"
    assert specs[0].modes == ("paper",)


def test_demo_validation_matrix_loads_with_small_matrix_setting() -> None:
    matrix_path = Path("docs/examples/demo_validation_matrix.json")
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    specs = load_validation_matrix(matrix_path)

    validate_matrix_completeness(specs, min_papers=int(payload["min_papers"]))
    assert len(specs) == 1
    assert len(specs[0].tasks) == 5


def test_demo_build_script_writes_only_to_local_runtime_dirs(tmp_path, monkeypatch) -> None:
    from genoscribe.storage import provenance_store

    spec = importlib.util.spec_from_file_location("demo_build_sample_corpus", "scripts/demo_build_sample_corpus.py")
    assert spec and spec.loader
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)

    data_dir = tmp_path / "src" / "genomics_assistant_data"
    library_dir = data_dir / "library"
    files_dir = data_dir / "library_files"
    stats_file = data_dir / "library_stats.json"

    monkeypatch.setattr(demo, "LIBRARY_DIR", library_dir)
    monkeypatch.setattr(demo, "LIBRARY_FILES_DIR", files_dir)
    monkeypatch.setattr(provenance_store, "LIBRARY_DIR", library_dir)
    monkeypatch.setattr(provenance_store, "STATS_FILE", stats_file)

    demo.build_demo_corpus()

    assert (files_dir / "genoscribe_demo_paper.md").exists()
    assert (library_dir / "genoscribe_demo_paper.json").exists()
    assert stats_file.exists()

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genoscribe.corpus import build_status, load_manifest, map_indexed_doc_ids_by_filename, summarize_specs
from genoscribe.schemas.document import DocumentIndex


def test_load_manifest_and_summary(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "documents": [
                    {
                        "slug": "doc-1",
                        "title": "Doc One",
                        "filename": "doc1.pdf",
                        "buckets": ["core_benchmark", "mode_specific"],
                        "modes": ["paper"],
                    },
                    {
                        "slug": "doc-2",
                        "title": "Doc Two",
                        "filename": "doc2.pdf",
                        "buckets": ["stress_test"],
                        "modes": ["variant"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    specs = load_manifest(manifest)
    summary = summarize_specs(specs)

    assert len(specs) == 2
    assert summary["buckets"]["core_benchmark"] == 1
    assert summary["buckets"]["stress_test"] == 1
    assert summary["modes"]["paper"] == 1
    assert summary["modes"]["variant"] == 1


def test_load_manifest_rejects_unknown_bucket(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "slug": "bad-doc",
                        "title": "Bad Doc",
                        "filename": "bad.pdf",
                        "buckets": ["totally_new_bucket"],
                        "modes": ["paper"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown buckets"):
        load_manifest(manifest)


def test_build_status_uses_disk_and_index_presence(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "slug": "doc-1",
                        "title": "Doc One",
                        "filename": "doc1.pdf",
                        "buckets": ["core_benchmark"],
                        "modes": ["paper"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    specs = load_manifest(manifest)
    files_dir = tmp_path / "library_files"
    files_dir.mkdir()
    (files_dir / "doc1.pdf").write_bytes(b"%PDF-1.7\n")

    doc = DocumentIndex(
        doc_id="doc-id-1",
        source_path=str(files_dir / "doc1.pdf"),
        ext=".pdf",
        title="Doc One",
        passages=[],
        vectors=[],
        term_counts=[],
        doc_lengths=[],
        doc_type="paper",
    )
    indexed = map_indexed_doc_ids_by_filename([doc])
    rows = build_status(specs=specs, library_files_dir=files_dir, indexed_doc_ids_by_filename=indexed)

    assert len(rows) == 1
    assert rows[0].file_present is True
    assert rows[0].indexed_doc_ids == ("doc-id-1",)


def test_load_manifest_rejects_duplicate_scope_aliases(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "slug": "doc-1",
                        "title": "Doc One",
                        "filename": "doc1.pdf",
                        "buckets": ["core_benchmark"],
                        "modes": ["paper"],
                        "scope_aliases": ["this plos paper"],
                    },
                    {
                        "slug": "doc-2",
                        "title": "Doc Two",
                        "filename": "doc2.pdf",
                        "buckets": ["generalization"],
                        "modes": ["paper"],
                        "scope_aliases": ["this plos paper"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate scope_alias"):
        load_manifest(manifest)

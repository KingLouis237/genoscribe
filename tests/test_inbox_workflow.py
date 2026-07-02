import genoscribe.app as app
import genoscribe.indexing as indexing


def test_list_inbox_files_filters_supported_extensions(monkeypatch, tmp_path):
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    monkeypatch.setattr(app, "INBOX_DIR", inbox_dir)

    keep = inbox_dir / "sample.pdf"
    keep.write_text("pdf payload", encoding="utf-8")
    (inbox_dir / "ignore.docx").write_text("nope", encoding="utf-8")

    files = app.list_inbox_files()
    assert [f.name for f in files] == [keep.name]


def test_add_path_to_library_copies_into_store(monkeypatch, tmp_path):
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    library_files = tmp_path / "store"
    library_files.mkdir()
    library_dir = tmp_path / "library"
    library_dir.mkdir()

    monkeypatch.setattr(app, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(app, "LIBRARY_FILES_DIR", library_files)
    monkeypatch.setattr(app, "LIBRARY_DIR", library_dir)
    monkeypatch.setattr(indexing, "LIBRARY_DIR", library_dir)

    sample = inbox_dir / "demo.txt"
    sample.write_text("Line one.\n\nLine two.", encoding="utf-8")

    docs = app.add_path_to_library(str(sample), {}, copy_source=True, delete_original=True)
    assert len(docs) == 1
    assert not sample.exists()
    assert any(library_files.iterdir()), "Copied file should exist in library store"
    assert len(list(library_dir.glob("*.json"))) == 1, "Document index should be saved"

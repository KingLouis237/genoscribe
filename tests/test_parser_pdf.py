import contextlib
from pathlib import Path

import pytest

from genoscribe.ingestion import parser_pdf


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    def __init__(self, *args, **kwargs) -> None:
        self.pages = [_FakePage("Hello world")]


def test_read_pdf_uses_logging_guard(monkeypatch, tmp_path):
    dummy = tmp_path / "dummy.pdf"
    dummy.write_bytes(b"%PDF-FAKE%")

    monkeypatch.setattr(parser_pdf, "HAS_PDFPLUMBER", False)
    monkeypatch.setattr(parser_pdf, "PdfReader", _FakeReader)

    calls = {"enter": 0, "exit": 0}

    @contextlib.contextmanager
    def fake_guard(level=None):
        calls["enter"] += 1
        yield True
        calls["exit"] += 1

    monkeypatch.setattr(parser_pdf, "_suppress_pypdf_logging", fake_guard)

    pages = parser_pdf.read_pdf(Path(dummy))

    assert pages == [(1, "Hello world")]
    assert calls == {"enter": 1, "exit": 1}


def test_read_pdf_raises_clean_error_on_reader_failure(monkeypatch, tmp_path):
    dummy = tmp_path / "broken.pdf"
    dummy.write_bytes(b"%PDF-FAKE%")

    monkeypatch.setattr(parser_pdf, "HAS_PDFPLUMBER", False)

    def boom(*args, **kwargs):
        raise ValueError("FloatObject (b'0.00-222')")

    monkeypatch.setattr(parser_pdf, "PdfReader", boom)

    exited = {"exit": False}

    @contextlib.contextmanager
    def fake_guard(level=None):
        try:
            yield True
        finally:
            exited["exit"] = True

    monkeypatch.setattr(parser_pdf, "_suppress_pypdf_logging", fake_guard)

    with pytest.raises(RuntimeError) as err:
        parser_pdf.read_pdf(Path(dummy))

    assert "broken.pdf" in str(err.value)
    assert "FloatObject" in str(err.value)
    assert exited["exit"]

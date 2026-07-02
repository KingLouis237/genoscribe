from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Iterator, List, Tuple

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .parser_text import clean_text

try:  # optional dependency
    import pdfplumber

    HAS_PDFPLUMBER = True
except Exception:  # pragma: no cover
    pdfplumber = None
HAS_PDFPLUMBER = False

LOGGER = logging.getLogger("genoscribe.ingestion")


@contextlib.contextmanager
def _suppress_pypdf_logging(level: int = logging.ERROR) -> Iterator[bool]:
    """Temporarily crank down the noisy pypdf loggers."""
    targets = [
        logging.getLogger("pypdf"),
        logging.getLogger("pypdf.generic"),
        logging.getLogger("pypdf.generic._base"),
    ]
    original_levels: List[int] = []
    changed = False
    for logger in targets:
        original_levels.append(logger.level)
        effective = logger.level if logger.level != logging.NOTSET else 0
        desired = level if effective == 0 or effective < level else logger.level
        if desired != logger.level:
            logger.setLevel(desired)
            changed = True
    try:
        yield changed
    finally:
        for logger, old in zip(targets, original_levels):
            # Restore original level (logging module treats 0 and NOTSET identically)
            logger.setLevel(old if old != 0 else logging.NOTSET)


def read_pdf(path: Path) -> List[Tuple[int, str]]:
    pages: List[Tuple[int, str]] = []

    if HAS_PDFPLUMBER and pdfplumber is not None:
        try:
            with pdfplumber.open(str(path)) as pdf:
                for i, page in enumerate(pdf.pages):
                    txt = page.extract_text() or ""
                    tables = page.extract_tables()
                    if tables:
                        table_text = "\n\n[TABLE]\n" + "\n".join(
                            " | ".join(str(cell) if cell else "" for cell in row)
                            for table in tables
                            for row in table
                        ) + "\n[/TABLE]\n\n"
                        txt += table_text

                    txt = clean_text(txt)
                    if txt:
                        pages.append((i + 1, txt))
            return pages
        except Exception:
            pass

    try:
        with _suppress_pypdf_logging() as suppressed:
            reader = PdfReader(str(path))
            for i, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                txt = clean_text(txt)
                if txt:
                    pages.append((i + 1, txt))
        if suppressed:
            LOGGER.debug("Suppressed malformed float warnings while parsing %s", path.name)
    except (PdfReadError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Failed to parse PDF {path.name}: {exc}. "
            "Try re-downloading the file or converting it via pdftotext/docling."
        ) from exc

    return pages


__all__ = ["read_pdf"]

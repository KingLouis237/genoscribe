from __future__ import annotations

import re
from pathlib import Path


GLUED_FLOAT_RE = re.compile(r"(\d+\.\d+)-(?=\d)")
GLUED_DIGIT_WORD_RE = re.compile(r"(\d)([A-Za-z])")
GLUED_WORD_DIGIT_RE = re.compile(r"([A-Za-z%])(\d)")


def _fix_glued_numbers(text: str) -> str:
    text = GLUED_FLOAT_RE.sub(r"\1 - ", text)
    text = GLUED_DIGIT_WORD_RE.sub(r"\1 \2", text)
    text = GLUED_WORD_DIGIT_RE.sub(r"\1 \2", text)
    return text


def clean_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = _fix_glued_numbers(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def read_text(path: Path) -> str:
    return clean_text(path.read_text(encoding="utf-8", errors="ignore"))


__all__ = ["clean_text", "read_text"]

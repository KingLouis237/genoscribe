from __future__ import annotations

from pathlib import Path


def infer_title(path: Path, text_sample: str) -> str:
    first_line = text_sample.strip().splitlines()[0] if text_sample.strip() else ""
    if 6 <= len(first_line) <= 120:
        return first_line
    return path.stem


__all__ = ["infer_title"]

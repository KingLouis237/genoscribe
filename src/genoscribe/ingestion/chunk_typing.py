from __future__ import annotations

import re
from typing import List

FIGURE_PREFIXES = (
    "figure",
    "fig.",
    "fig ",
    "supplementary figure",
    "supplementary fig",
    "extended data figure",
    "ext. data fig",
)

TABLE_PREFIXES = (
    "table",
    "supplementary table",
    "extended data table",
)

PANEL_PREFIX = re.compile(r"^(?:panel\s+)?([a-k]|\([a-k]\)|[a-k][\).:])", re.IGNORECASE)
SINGLE_LETTER_RE = re.compile(r"^[a-k]$", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z]+")


def _first_nonempty_lines(text: str, limit: int = 3) -> List[str]:
    lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= limit:
            break
    return lines


def _digit_ratio(text: str) -> float:
    digits = sum(ch.isdigit() for ch in text)
    return digits / max(1, len(text))


def _contains_keyword_chunk(text: str, keywords: tuple[str, ...]) -> bool:
    snippet = text[:220].lower()
    return any(token in snippet for token in keywords)


def _looks_like_panel_block(lines: List[str]) -> bool:
    if not lines:
        return False
    first = lines[0]
    if not SINGLE_LETTER_RE.match(first):
        return False
    # treat up to 3 leading lines that are single letters as panel markers
    sequential_letters = 0
    for line in lines[:3]:
        if SINGLE_LETTER_RE.match(line):
            sequential_letters += 1
        else:
            break
    return sequential_letters >= 1


def _axis_heavy(lines: List[str]) -> bool:
    if not lines:
        return False
    axisish = 0
    for line in lines:
        letters = WORD_RE.findall(line)
        digits = sum(ch.isdigit() for ch in line)
        if digits and digits / max(1, len(line)) > 0.6:
            axisish += 1
            continue
        if letters and all(len(word) <= 4 for word in letters):
            axisish += 1
    return axisish / len(lines) >= 0.5


def classify_chunk(
    *,
    raw_text: str | None,
    clean_text: str | None,
    is_table_or_figure: bool,
    noise_level: float | None = None,
) -> str:
    raw = (raw_text or "").strip()
    clean = (clean_text or raw).strip()
    lines = _first_nonempty_lines(clean, limit=4)
    first_line = lines[0].lower() if lines else ""
    lower_clean = clean.lower()
    intro_block = " ".join(lines[:2]).lower()
    digits_ratio = _digit_ratio(clean)

    if is_table_or_figure:
        if any(first_line.startswith(pref) for pref in TABLE_PREFIXES) or "table" in intro_block:
            return "table"
        if any(first_line.startswith(pref) for pref in FIGURE_PREFIXES) or PANEL_PREFIX.match(first_line):
            return "caption"
        if "panel" in lower_clean[:160] or _looks_like_panel_block(lines):
            return "caption"
        return "figure_derived"

    if any(first_line.startswith(pref) for pref in TABLE_PREFIXES) or _contains_keyword_chunk(lower_clean, TABLE_PREFIXES):
        return "table"
    if (
        any(first_line.startswith(pref) for pref in FIGURE_PREFIXES)
        or _contains_keyword_chunk(lower_clean, FIGURE_PREFIXES)
        or PANEL_PREFIX.match(first_line)
        or (_looks_like_panel_block(lines) and _contains_keyword_chunk(lower_clean, FIGURE_PREFIXES))
    ):
        return "caption"

    ratio = noise_level if noise_level is not None and noise_level > 0 else digits_ratio
    if ratio >= 0.65 or _axis_heavy(lines):
        return "figure_derived"
    if ratio >= 0.45:
        return "mixed"
    return "body"


__all__ = ["classify_chunk"]

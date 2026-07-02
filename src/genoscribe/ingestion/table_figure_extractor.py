from __future__ import annotations

import re
from typing import List, Optional, Tuple

AXIS_NOISE_RE = re.compile(r"^[\d\s\.,:;/\\\-–%]+$")
SHORT_UPPER_RE = re.compile(r"^[A-Z][A-Za-z0-9/\- ]{0,30}$")
AXIS_KEYWORDS = {
    "pathogenic",
    "benign",
    "aupr",
    "auc",
    "pllr",
    "clinvar",
    "genes",
    "no skill",
    "baseline",
    "cm",
    "arm",
    "vus",
    "pathogenic/likely_pathogenic",
    "likely_pathogenic",
    "benign/likely_benign",
    "likely_benign",
    "baseline",
    "cm",
    "arm",
    "vus",
    "precision",
    "recall",
}

NUMERIC_RUN_RE = re.compile(r"(?:\d+(?:\.\d+)?\s+){4,}\d")
LETTER_RATIO_RE = re.compile(r"[A-Za-z]")

SUMMARY_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
METRIC_HINT_RE = re.compile(
    r"(p\s*=\s*[\d\.e-]+|auc|aupr|kl divergence|accuracy|precision|recall|baseline)",
    re.IGNORECASE,
)


def detect_table_or_figure(text: str) -> bool:
    if re.search(r"(?i)(table|figure|fig\.?)\s+\d+", text[:200]):
        return True

    lines = text.split("\n")
    if len(lines) > 2:
        tab_count = sum(1 for line in lines if "\t" in line or "|" in line)
        if tab_count > len(lines) * 0.5:
            return True

    numbers = re.findall(r"\d+\.?\d*", text)
    if len(numbers) > 20 and len(text) < 500:
        return True

    return False


def _looks_like_axis_label(line: str) -> bool:
    lower = line.lower()
    if AXIS_NOISE_RE.match(lower):
        return True
    if NUMERIC_RUN_RE.search(lower):
        return True
    letters = LETTER_RATIO_RE.findall(lower)
    if not letters:
        return True
    digits = sum(ch.isdigit() for ch in lower)
    if digits and digits / max(1, len(lower)) > 0.55:
        return True
    words = line.split()
    if len(words) <= 3 and not any(ch in line for ch in ".:;,%"):
        if lower in AXIS_KEYWORDS or (SHORT_UPPER_RE.match(line) and line.upper() == line):
            return True
        if all(word.lower() in AXIS_KEYWORDS for word in words):
            return True
    return False


def strip_figure_noise(text: str, figure_mode: bool) -> Tuple[str, float]:
    if not text:
        return "", 0.0
    lines: List[str] = []
    removed = 0
    total = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            lines.append("")
            continue
        total += 1
        if figure_mode and _looks_like_axis_label(stripped):
            removed += 1
            continue
        lines.append(stripped)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), (removed / total) if total else 0.0


def build_passage_summary(text: str, prefer_metrics: bool) -> Optional[str]:
    if not text:
        return None

    sentences = [s.strip() for s in SUMMARY_SENTENCE_RE.split(text) if s.strip()]
    candidates = [s for s in sentences if len(s.split()) >= 6]
    if candidates:
        if prefer_metrics:
            for s in candidates:
                if METRIC_HINT_RE.search(s):
                    return s[:280]
        return candidates[0][:280]

    metric_lines = []
    for line in text.splitlines():
        if METRIC_HINT_RE.search(line):
            metric_lines.append(line.strip())
        if len(metric_lines) >= 2:
            break
    if metric_lines:
        return " ".join(metric_lines)[:280]
    return None


def is_figure_like(text: str) -> bool:
    if not text:
        return False
    if detect_table_or_figure(text):
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        axisish = sum(1 for line in lines if _looks_like_axis_label(line))
        if axisish and axisish / len(lines) >= 0.4:
            return True
    digits = sum(ch.isdigit() for ch in text)
    if digits and digits / max(1, len(text)) >= 0.3:
        return True
    return False


__all__ = [
    "detect_table_or_figure",
    "strip_figure_noise",
    "build_passage_summary",
    "is_figure_like",
]

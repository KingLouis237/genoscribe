from __future__ import annotations

import re
from typing import List

SHORT_TOKEN_PATTERN = re.compile(r"\b[A-Z]{2,4}\b")

LONG_FORM_HINTS = {
    "cm": "cardiomyopathy",
    "arm": "arrhythmia",
    "vus": "variant of uncertain significance",
    "afr": "African ancestry",
    "eur": "European ancestry",
    "pllr": "pseudo-log-likelihood ratio",
    "auc": "area under the ROC curve",
    "mcv": "mean corpuscular volume",
}


def extract_short_tokens(text: str) -> List[str]:
    if not text:
        return []
    tokens = []
    for match in SHORT_TOKEN_PATTERN.findall(text):
        normalized = match.lower()
        tokens.append(normalized)
    return tokens


def suggested_long_form(token: str) -> str:
    return LONG_FORM_HINTS.get(token.lower(), "")


__all__ = ["extract_short_tokens", "suggested_long_form", "LONG_FORM_HINTS"]

from __future__ import annotations

import re
import unicodedata
from typing import List

from .table_figure_extractor import detect_table_or_figure

GREEK_MAP = {
    "\u03b1": "alpha",
    "\u03b2": "beta",
    "\u03b3": "gamma",
    "\u03b4": "delta",
    "\u03b5": "epsilon",
    "\u03b6": "zeta",
    "\u03b7": "eta",
    "\u03b8": "theta",
    "\u03b9": "iota",
    "\u03ba": "kappa",
    "\u03bb": "lambda",
    "\u03bc": "mu",
    "\u03bd": "nu",
    "\u03be": "xi",
    "\u03c0": "pi",
    "\u03c1": "rho",
    "\u03c3": "sigma",
    "\u03c4": "tau",
    "\u03c5": "upsilon",
    "\u03c6": "phi",
    "\u03c7": "chi",
    "\u03c8": "psi",
    "\u03c9": "omega",
    "\u0391": "alpha",
    "\u0392": "beta",
    "\u0393": "gamma",
    "\u0394": "delta",
    "\u0395": "epsilon",
    "\u0396": "zeta",
    "\u0397": "eta",
    "\u0398": "theta",
    "\u0399": "iota",
    "\u039a": "kappa",
    "\u039b": "lambda",
    "\u039c": "mu",
    "\u039d": "nu",
    "\u039e": "xi",
    "\u03a0": "pi",
    "\u03a1": "rho",
    "\u03a3": "sigma",
    "\u03a4": "tau",
    "\u03a5": "upsilon",
    "\u03a6": "phi",
    "\u03a7": "chi",
    "\u03a8": "psi",
    "\u03a9": "omega",
}

TOKEN_PATTERNS = [
    r"rs\d+",
    r"(?:[cgp]\.)[0-9A-Za-z_\-\+\>\=\(\)\[\]\.:/]+",
    r"[A-Za-z]{1,4}\d{1,6}(?:\.\d+)?",
    r"[A-Za-z0-9]+(?:[-_/\.][A-Za-z0-9]+)+",
    r"[A-Za-z0-9]{2,}",
]
TOKEN_RE = re.compile("|".join(f"(?:{p})" for p in TOKEN_PATTERNS))


def normalize_genomics_text(s: str) -> str:
    if not s:
        return ""

    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)

    for greek, ascii_equiv in GREEK_MAP.items():
        s = s.replace(greek, ascii_equiv)

    s = s.replace("\r\n", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def tokenize_genomics(text: str) -> List[str]:
    text = normalize_genomics_text(text).lower()
    return TOKEN_RE.findall(text)


def chunk_text(
    text: str,
    target_size: int,
    max_size: int,
    overlap_paras: int,
) -> List[str]:
    text = normalize_genomics_text(text)
    if not text:
        return []

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []

    chunks: List[str] = []
    buf: List[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if buf:
            chunk = "\n\n".join(buf).strip()
            if detect_table_or_figure(chunk):
                chunk = "[TABLE/FIGURE]\n" + chunk
            chunks.append(chunk)
        buf.clear()
        buf_len = 0

    for p in paras:
        plen = len(p)
        if plen > max_size:
            flush()
            start = 0
            while start < plen:
                end = min(plen, start + max_size)
                chunks.append(p[start:end].strip())
                start = end
            continue

        if buf_len + plen + 2 <= target_size:
            buf.append(p)
            buf_len += plen + 2
        else:
            flush()
            buf.append(p)
            buf_len = plen

    flush()

    if overlap_paras > 0 and len(chunks) > 1:
        overlapped: List[str] = []
        prev_paras: List[str] = []

        for c in chunks:
            clean_chunk = c.replace("[TABLE/FIGURE]\n", "")
            current_paras = [p.strip() for p in re.split(r"\n\s*\n", clean_chunk) if p.strip()]
            prefix = "\n\n".join(prev_paras[-overlap_paras:]).strip()
            overlapped_chunk = (prefix + "\n\n" + c).strip() if prefix else c
            overlapped.append(overlapped_chunk)
            prev_paras = current_paras

        chunks = overlapped

    return [c for c in chunks if c.strip()]


__all__ = ["normalize_genomics_text", "tokenize_genomics", "chunk_text"]

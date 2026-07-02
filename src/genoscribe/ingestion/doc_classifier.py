from __future__ import annotations

from typing import Iterable

DOC_TYPE_KEYWORDS = {
    "assembly": (
        "assembly",
        "busco",
        "quast",
        "kat",
        "bandage",
        "scaffold",
        "contig",
        "n50",
        "ng50",
        "coverage",
        "shine",
    ),
    "variant": (
        "variant",
        "clinvar",
        "missense",
        "pathogenic",
        "pllr",
        "allele",
        "cohort",
        "genotype",
        "varcopp",
        "m-cap",
        "revel",
    ),
}


def _count_hits(blob: str, keywords: Iterable[str]) -> int:
    lowered = blob.lower()
    return sum(1 for token in keywords if token in lowered)


def infer_document_type(source_name: str, title: str | None, sample_texts: Iterable[str]) -> str:
    source_lower = source_name.lower()
    if "shine" in source_lower:
        return "assembly"
    blob_parts = [source_lower]
    if title:
        blob_parts.append(title.lower())
    for text in sample_texts:
        if text:
            blob_parts.append(text.lower())
    blob = " \n".join(blob_parts)
    scores = {label: _count_hits(blob, tokens) for label, tokens in DOC_TYPE_KEYWORDS.items()}
    assembly = scores["assembly"]
    variant = scores["variant"]
    if assembly >= max(2, variant + 1):
        return "assembly"
    if variant >= max(2, assembly + 1):
        return "variant"
    return "paper"


__all__ = ["infer_document_type"]

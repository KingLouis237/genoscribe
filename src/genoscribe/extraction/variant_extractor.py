from __future__ import annotations

from typing import List, Optional

from genoscribe.reasoning.evidence_bundle import VariantEvidenceBundle, assemble_variant_evidence
from genoscribe.schemas.document import Passage


def extract_variant_assessment(
    passages: List[Passage],
    variant_id: Optional[str] = None,
    phenotype: Optional[str] = None,
    query: Optional[str] = None,
) -> VariantEvidenceBundle:
    return assemble_variant_evidence(passages, query=query, variant_id=variant_id, phenotype=phenotype)


__all__ = ["extract_variant_assessment"]

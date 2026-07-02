from __future__ import annotations

from typing import List, Tuple

from genoscribe.schemas.document import Passage


class EvidenceVerifier:
    def verify(self, passages: List[Passage]) -> Tuple[bool, List[str]]:
        warnings: List[str] = []
        for passage in passages:
            if not passage.text.strip():
                warnings.append(f"Empty passage detected for {passage.doc_id}:{passage.chunk_id}")
        return (len(warnings) == 0, warnings)


__all__ = ["EvidenceVerifier"]

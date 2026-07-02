from __future__ import annotations

from typing import List

from genoscribe.modes.assembly_mode import AssemblyMode
from genoscribe.modes.paper_mode import PaperMode
from genoscribe.modes.variant_mode import VariantMode
from genoscribe.schemas.document import Passage


class EvidenceSynthesizer:
    def __init__(self) -> None:
        self.paper = PaperMode()
        self.assembly = AssemblyMode()
        self.variant = VariantMode()

    def synthesize(self, mode: str, passages: List[Passage], **kwargs) -> str:
        mode = (mode or "paper").lower()
        if mode == "assembly":
            return self.assembly.generate(passages, kwargs.get("sample_id"))
        if mode == "variant":
            return self.variant.generate(
                passages,
                kwargs.get("variant_id"),
                kwargs.get("phenotype"),
                kwargs.get("query"),
            )
        return self.paper.generate(
            passages,
            kwargs.get("title", "Paper synthesis"),
            query=kwargs.get("query"),
            target_doc_ids=kwargs.get("target_doc_ids"),
        )


__all__ = ["EvidenceSynthesizer"]

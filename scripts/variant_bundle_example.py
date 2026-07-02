from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from genoscribe.reasoning.evidence_bundle import assemble_variant_evidence
from genoscribe.schemas.document import Passage


def _sample_passages() -> list[Passage]:
    text = (
        "ClinVar reports TTN c.123A>T as pathogenic for cardiomyopathy with 42 cases and 10 controls; "
        "gnomAD frequency 0.0001. African ancestry enrichment noted."
    )
    return [
        Passage(
            doc_id="DYNA",
            source_path="DYNA_2026-03-09_18-53-20.pdf",
            page=18,
            chunk_id=39,
            text=text,
            summary="TTN variant cardiomyopathy summary",
            chunk_type="body",
            doc_type="variant",
            metrics=[
                {
                    "label": "PLLR",
                    "value": "13.28",
                    "model": "DYNA",
                    "dataset": "CM",
                    "task": "pathogenicity",
                    "chunk_id": 39,
                    "source_doc_id": "DYNA",
                    "source_path": "DYNA_2026-03-09_18-53-20.pdf",
                    "context": "Cardiomyopathy PLLR distribution",
                    "page": 18,
                }
            ],
            short_tokens=["cm", "afr"],
        )
    ]


def main() -> None:
    passages = _sample_passages()
    bundle = assemble_variant_evidence(
        passages,
        query="TTN cardiomyopathy African ancestry PLLR",
        variant_id="c.123A>T",
        phenotype="cardiomyopathy",
    )
    output_dir = Path("src/genomics_assistant_data/outputs/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"variant_bundle_example_{timestamp}.json"
    payload = {
        "candidates": [asdict(candidate) for candidate in bundle.candidates],
        "coverage": asdict(bundle.coverage),
        "contradictions": bundle.contradictions,
    }
    output_path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote variant bundle example to {output_path}")


if __name__ == "__main__":
    main()

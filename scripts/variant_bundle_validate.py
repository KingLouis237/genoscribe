from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from genoscribe.reasoning.evidence_bundle import assemble_variant_evidence
from genoscribe.schemas.document import Passage

CONFIG: List[Dict[str, Optional[str]]] = [
    {
        "label": "DYNA cardiomyopathy",
        "filename": "DYNA_2026-03-09_18-53-20-1773078800.json",
        "query": "cardiomyopathy arrhythmia DYNA variant pathogenicity PLLR",
        "phenotype": "cardiomyopathy",
    },
    {
        "label": "Varipred LMNA",
        "filename": "Varipred_2026-03-09_18-53-16-1773078796.json",
        "query": "LMNA arrhythmia variant combination Varipred",
        "phenotype": "arrhythmia",
    },
    {
        "label": "VarCoPP combinations",
        "filename": "papadimitriou-et-al-2019-predicting-disease-causing-variant-combinations_1__2026-03-09_18-53-49-1773772719.json",
        "query": "VarCoPP support score confidence zone combination pathogenicity",
        "phenotype": "cardiomyopathy",
    },
    {
        "label": "Marsh cardiomyopathy",
        "filename": "Marsh_et_al_Pred_variants_2026-03-09_18-50-41-1773078641.json",
        "query": "cardiomyopathy LMNA TTN Marsh variant evaluation",
        "phenotype": "cardiomyopathy",
    },
    {
        "label": "Varcopp Nassim",
        "filename": "Varcopp_Nassim_2026-03-09_18-53-41-1773078821.json",
        "query": "Varcopp compound heterozygous pathogenic combination",
        "phenotype": "arrhythmia",
    },
]


def load_passages(path: Path) -> List[Passage]:
    data = json.loads(path.read_text(encoding="utf-8"))
    passages = [Passage(**item) for item in data.get("passages", [])]
    return passages


def summarize_variant_bundle(doc_label: str, passages: List[Passage], query: str, phenotype: Optional[str], variant_id: Optional[str]) -> Dict[str, Any]:
    bundle = assemble_variant_evidence(passages, query=query, variant_id=variant_id, phenotype=phenotype)
    summary: Dict[str, Any] = {
        "label": doc_label,
        "query": query,
        "phenotype_hint": phenotype,
        "variant_id_hint": variant_id,
        "candidate_count": len(bundle.candidates),
        "coverage": asdict(bundle.coverage),
        "contradictions": bundle.contradictions,
        "candidates": [],
    }
    for candidate in bundle.candidates:
        summary["candidates"].append(
            {
                "variant_id": candidate.variant_id,
                "gene": candidate.gene,
                "clinvar_significance": candidate.clinvar_significance,
                "ancestry": candidate.ancestry,
                "cohort": candidate.cohort,
                "case_count": candidate.case_count,
                "control_count": candidate.control_count,
                "gnomad_frequency": candidate.gnomad_frequency,
                "metrics": [
                    {
                        "label": metric.label,
                        "value": metric.value,
                        "model": metric.model,
                        "dataset": metric.dataset,
                        "task": metric.task,
                        "chunk_type": metric.chunk_type,
                    }
                    for metric in candidate.pathogenicity_metrics[:3]
                ],
                "confidence": candidate.confidence,
                "confidence_reason": candidate.confidence_reason,
                "chunk_type": candidate.chunk_type,
                "doc_type": candidate.doc_type,
            }
        )
    return summary


def main() -> None:
    library_dir = Path("src/genomics_assistant_data/library")
    results: List[Dict[str, Any]] = []
    for entry in CONFIG:
        filename = entry["filename"]
        if not filename:
            continue
        path = library_dir / filename
        if not path.exists():
            continue
        passages = load_passages(path)
        summary = summarize_variant_bundle(
            doc_label=entry["label"] or filename,
            passages=passages,
            query=entry.get("query") or "",
            phenotype=entry.get("phenotype"),
            variant_id=entry.get("variant_id"),
        )
        results.append(summary)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path("src/genomics_assistant_data/outputs/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"variant_bundle_validation_{timestamp}.json"
    output_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"Wrote validation summary to {output_path}")


if __name__ == "__main__":
    main()

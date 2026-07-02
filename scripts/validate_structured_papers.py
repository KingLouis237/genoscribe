from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from genoscribe.reasoning.evidence_bundle import assemble_paper_evidence
from genoscribe.reasoning.structured_synthesizer import (
    PaperStructuredRenderer,
    StructuredPaperSynthesizer,
    StructuredVerifier,
)
from genoscribe.schemas.document import Passage

DOCS = [
    ("DYNA_2026-03-09_18-53-20-1773078800.json", "DYNA cardiomyopathy pathogenicity metrics"),
    ("Gene-Pathogenicity-Prediction-using-Genomic-Foundation-Models_2026-03-09_18-50-46-1773078646.json", "foundation model pathogenicity benchmarks"),
    ("Frazer_et_al_EVE_2026-03-09_18-50-42-1773078642.json", "evolutionary model gene coverage"),
    ("King_et_al_Discordance_2026-03-09_18-50-38-1773078638.json", "clinical discordance analysis"),
    ("Marsh_et_al_Pred_variants_2026-03-09_18-50-41-1773078641.json", "cardiomyopathy variant evaluation"),
]


def load_passages(doc_name: str, max_passages: Optional[int] = None) -> List[Passage]:
    path = Path("src/genomics_assistant_data/library") / doc_name
    data = json.loads(path.read_text(encoding="utf-8"))
    passages = [Passage(**item) for item in data.get("passages", [])]
    if max_passages:
        return passages[:max_passages]
    return passages


def main() -> None:
    synthesizer = StructuredPaperSynthesizer()
    verifier = StructuredVerifier()
    renderer = PaperStructuredRenderer()
    output_dir = Path("src/genomics_assistant_data/outputs/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary = []

    for doc_name, query in DOCS:
        passages = load_passages(doc_name, max_passages=10)
        bundle = assemble_paper_evidence(passages, query=query)
        structured = synthesizer.build(bundle, title=f"Structured summary for {doc_name}", query=query)
        verified = verifier.verify(structured)
        prose = renderer.render(verified)

        safe_name = doc_name.replace(".json", "")
        json_path = output_dir / f"structured_{safe_name}_{timestamp}.json"
        txt_path = output_dir / f"structured_{safe_name}_{timestamp}.txt"
        json_path.write_text(json.dumps(asdict(verified), indent=2), encoding="utf-8")
        txt_path.write_text(prose, encoding="utf-8")

        summary.append(
            {
                "doc": doc_name,
                "query": query,
                "supported_claims": len(verified.supported_claims),
                "unsupported": len(verified.unsupported_claims),
                "conflicts": len(verified.conflicts),
                "render_status": verified.audit.render_status,
                "json_path": str(json_path),
                "text_path": str(txt_path),
            }
        )

    print(json.dumps({"runs": summary}, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from genoscribe.reasoning.evidence_bundle import assemble_paper_evidence
from genoscribe.reasoning.structured_synthesizer import PaperStructuredRenderer, StructuredPaperSynthesizer, StructuredVerifier
from genoscribe.schemas.document import Passage


def load_passages(doc_name: str) -> list[Passage]:
    path = Path("src/genomics_assistant_data/library") / doc_name
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Passage(**item) for item in data.get("passages", [])]


def main() -> None:
    doc_name = "DYNA_2026-03-09_18-53-20-1773078800.json"
    passages = load_passages(doc_name)[:6]
    bundle = assemble_paper_evidence(passages, query="DYNA cardiomyopathy pathogenicity metrics")
    synthesizer = StructuredPaperSynthesizer()
    verifier = StructuredVerifier()
    renderer = PaperStructuredRenderer()

    structured = synthesizer.build(bundle, title="DYNA structured summary", query="DYNA cardiomyopathy pathogenicity metrics")
    verified = verifier.verify(structured)
    prose = renderer.render(verified)

    output_dir = Path("src/genomics_assistant_data/outputs/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    structured_path = output_dir / f"structured_paper_{timestamp}.json"
    prose_path = output_dir / f"structured_paper_{timestamp}.txt"

    structured_path.write_text(json.dumps(asdict(verified), indent=2), encoding="utf-8")
    prose_path.write_text(prose, encoding="utf-8")
    print(f"Wrote structured artifact to {structured_path}")


if __name__ == "__main__":
    main()

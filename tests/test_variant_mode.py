from __future__ import annotations

from genoscribe.modes.variant_mode import VariantMode
from genoscribe.reasoning.evidence_bundle import assemble_variant_evidence
from genoscribe.schemas.document import Passage


def _sample_passage(text: str, chunk_id: int) -> Passage:
    return Passage(
        doc_id="doc_variant",
        source_path="doc_variant.pdf",
        page=3,
        chunk_id=chunk_id,
        text=text,
        summary="ClinVar variant summary",
        chunk_type="body",
        doc_type="variant",
        metrics=[
            {
                "label": "PLLR",
                "value": "13.2",
                "model": "DYNA",
                "dataset": "CM",
                "task": "pathogenicity",
                "chunk_id": chunk_id,
                "source_doc_id": "doc_variant",
                "source_path": "doc_variant.pdf",
                "context": "Pathogenic PLLR comparison",
                "page": 3,
            }
        ],
        short_tokens=["afr"],
    )


def test_assemble_variant_evidence_extracts_variant_fields():
    passage = _sample_passage(
        "ClinVar classifies TTN c.123A>T variant as pathogenic in a cardiomyopathy cohort "
        "with 42 cases and 10 controls; gnomAD frequency 0.0001 in African ancestry.",
        chunk_id=11,
    )
    bundle = assemble_variant_evidence(
        [passage],
        query="TTN cardiomyopathy African ancestry",
        variant_id="c.123A>T",
        phenotype="cardiomyopathy",
    )
    assert bundle.candidates, "Expected one candidate"
    candidate = bundle.candidates[0]
    assert candidate.variant_id == "c.123A>T"
    assert candidate.gene == "TTN"
    assert candidate.clinvar_significance == "Pathogenic"
    assert candidate.case_count == 42
    assert candidate.control_count == 10
    assert "Missing query terms" not in "\n".join(bundle.coverage.notes)


def test_variant_mode_reports_contradictions():
    patho = _sample_passage(
        "ClinVar review: LMNA c.456G>A is classified as likely pathogenic for arrhythmia.",
        chunk_id=20,
    )
    benign = _sample_passage(
        "ClinVar classification lists LMNA c.456G>A as benign in a European control cohort.",
        chunk_id=21,
    )
    bundle = assemble_variant_evidence([patho, benign], variant_id="c.456G>A")
    assert bundle.contradictions, "Conflicting classifications should be surfaced"

    renderer = VariantMode()
    report = renderer.generate([patho, benign], variant_id="c.456G>A", query="LMNA arrhythmia")
    assert "Variant evidence for c.456G>A" in report
    assert "Conflicting ClinVar significance" in report
    assert "Missing fields" in report, "Coverage summary should include missing context"

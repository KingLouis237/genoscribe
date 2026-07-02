from __future__ import annotations

from genoscribe.reasoning.evidence_bundle import assemble_paper_evidence
from genoscribe.reasoning.structured_synthesizer import (
    PaperStructuredRenderer,
    StructuredPaperSynthesizer,
    StructuredVerifier,
)
from genoscribe.schemas.document import Passage


def _sample_passage(chunk_id: int, text: str, metrics=None) -> Passage:
    return Passage(
        doc_id="doc1",
        source_path="doc1.pdf",
        page=1,
        chunk_id=chunk_id,
        text=text,
        summary="summary",
        metrics=metrics or [],
        chunk_type="body",
        doc_type="paper",
    )


def test_structured_synthesizer_builds_claims_with_citations():
    metric = {
        "label": "AUPR",
        "value": "0.91",
        "model": "ModelX",
        "dataset": "ClinVar",
        "task": "pathogenicity",
        "chunk_id": 0,
        "source_doc_id": "doc1",
        "source_path": "doc1.pdf",
        "context": "Metric context",
        "page": 1,
    }
    passage = _sample_passage(0, "ModelX achieved AUPR 0.91 on ClinVar.", metrics=[metric])
    bundle = assemble_paper_evidence([passage], query="ModelX AUPR ClinVar")
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="ModelX AUPR ClinVar")
    assert structured.supported_claims, "expected at least one supported claim"
    claim = structured.supported_claims[0]
    assert claim.citations and claim.citations[0].chunk_id == 0
    assert structured.metric_summaries

    verifier = StructuredVerifier()
    verified = verifier.verify(structured)
    assert verified.supported_claims, "claim should survive verifier"

    renderer = PaperStructuredRenderer()
    prose = renderer.render(verified)
    assert "Supported claims" in prose
    assert "ModelX" in prose


def test_missing_terms_create_unsupported_claims():
    passage = _sample_passage(0, "General discussion")
    bundle = assemble_paper_evidence([passage], query="rare disease mechanism")
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="rare disease mechanism")
    assert structured.unsupported_claims, "missing query terms should surface unsupported claims"
    assert structured.unsupported_claims[0].status == "insufficient_evidence"


def test_off_target_audit_flagged_when_target_docs_missing():
    passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=0,
        text="Unrelated discussion",
        summary="summary",
        metrics=[],
        chunk_type="body",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence([passage], query="DYNA pathogenicity", target_doc_ids=["dyna_doc"])
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="DYNA pathogenicity")
    assert structured.audit.render_status == "off_target_evidence"
    assert any("Target documents not represented" in note.description for note in structured.limitations)


def test_framing_terms_excluded_from_missing_terms():
    passage = _sample_passage(0, "DYNA benchmarking details")
    bundle = assemble_paper_evidence([passage], query="DYNA paper")
    assert "paper" not in bundle.coverage.missing_terms


def test_metric_intent_without_metrics_is_insufficient():
    passage = _sample_passage(0, "Narrative summary without explicit extracted metrics.")
    bundle = assemble_paper_evidence([passage], query="report AUPR precision recall metrics")
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="report AUPR precision recall metrics")
    assert structured.audit.render_status == "insufficient_evidence"
    assert any("quantitative metrics" in item.topic.lower() for item in structured.unsupported_claims)


def test_off_target_when_supported_claims_cite_only_non_target_docs():
    non_target_metric = {
        "label": "AUPR",
        "value": "0.88",
        "model": "ModelY",
        "dataset": "Benchmark",
        "task": "PR-AUC",
        "chunk_id": 1,
        "source_doc_id": "other_doc",
        "source_path": "other_doc.pdf",
        "context": "",
        "page": 1,
    }
    target_passage = Passage(
        doc_id="target_doc",
        source_path="target_doc.pdf",
        page=1,
        chunk_id=0,
        text="General background text.",
        summary="General background text.",
        metrics=[],
        chunk_type="body",
        doc_type="paper",
    )
    other_passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=1,
        text="ModelY reported AUPR 0.88.",
        summary="ModelY reported AUPR 0.88.",
        metrics=[non_target_metric],
        chunk_type="caption",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence([target_passage, other_passage], query="AUPR", target_doc_ids=["target_doc"])
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="AUPR")
    assert structured.audit.render_status == "off_target_evidence"
    assert any("non-target documents" in note.description for note in structured.limitations)


def test_scoped_metric_intent_prefers_target_metric_provenance():
    non_target_metric = {
        "label": "AUPR",
        "value": "0.88",
        "model": "ModelY",
        "dataset": "Benchmark",
        "task": "PR-AUC",
        "chunk_id": 0,
        "source_doc_id": "other_doc",
        "source_path": "other_doc.pdf",
        "context": "",
        "page": 1,
    }
    target_metric = {
        "label": "AUPR",
        "value": "0.91",
        "model": "TargetModel",
        "dataset": "Benchmark",
        "task": "PR-AUC",
        "chunk_id": 1,
        "source_doc_id": "target_doc",
        "source_path": "target_doc.pdf",
        "context": "",
        "page": 1,
    }
    non_target_passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=0,
        text="ModelY AUPR 0.88",
        summary="ModelY AUPR 0.88",
        metrics=[non_target_metric],
        chunk_type="caption",
        doc_type="paper",
    )
    target_passage = Passage(
        doc_id="target_doc",
        source_path="target_doc.pdf",
        page=1,
        chunk_id=1,
        text="TargetModel AUPR 0.91",
        summary="TargetModel AUPR 0.91",
        metrics=[target_metric],
        chunk_type="caption",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence(
        [non_target_passage, target_passage],
        query="AUPR metrics",
        target_doc_ids=["target_doc"],
    )
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="AUPR metrics")
    assert structured.supported_claims
    assert structured.supported_claims[0].citations[0].doc_id == "target_doc"


def test_scoped_metric_intent_with_target_metric_is_not_off_target():
    target_metric = {
        "label": "AUPR",
        "value": "0.91",
        "model": "TargetModel",
        "dataset": "Benchmark",
        "task": "PR-AUC",
        "chunk_id": 0,
        "source_doc_id": "target_doc",
        "source_path": "target_doc.pdf",
        "context": "",
        "page": 1,
    }
    target_passage = Passage(
        doc_id="target_doc",
        source_path="target_doc.pdf",
        page=1,
        chunk_id=0,
        text="TargetModel AUPR 0.91",
        summary="TargetModel AUPR 0.91",
        metrics=[target_metric],
        chunk_type="caption",
        doc_type="paper",
    )
    non_target_passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=1,
        text="Other metric discussion",
        summary="Other metric discussion",
        metrics=[],
        chunk_type="body",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence(
        [non_target_passage, target_passage],
        query="AUPR metrics",
        target_doc_ids=["target_doc"],
    )
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="AUPR metrics")
    assert structured.audit.render_status != "off_target_evidence"


def test_scoped_metric_intent_without_target_metrics_stays_off_target():
    non_target_metric = {
        "label": "AUPR",
        "value": "0.88",
        "model": "ModelY",
        "dataset": "Benchmark",
        "task": "PR-AUC",
        "chunk_id": 1,
        "source_doc_id": "other_doc",
        "source_path": "other_doc.pdf",
        "context": "",
        "page": 1,
    }
    target_passage = Passage(
        doc_id="target_doc",
        source_path="target_doc.pdf",
        page=1,
        chunk_id=0,
        text="Target narrative only",
        summary="Target narrative only",
        metrics=[],
        chunk_type="body",
        doc_type="paper",
    )
    non_target_passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=1,
        text="ModelY reported AUPR 0.88",
        summary="ModelY reported AUPR 0.88",
        metrics=[non_target_metric],
        chunk_type="caption",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence(
        [target_passage, non_target_passage],
        query="AUPR metrics",
        target_doc_ids=["target_doc"],
    )
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(bundle, title="Test", query="AUPR metrics")
    assert structured.audit.render_status == "off_target_evidence"


def test_scoped_non_metric_without_target_coverage_is_insufficient_not_off_target():
    non_target_metric = {
        "label": "AUPR",
        "value": "0.81",
        "model": "OtherModel",
        "dataset": "Benchmark",
        "task": "classification",
        "chunk_id": 0,
        "source_doc_id": "other_doc",
        "source_path": "other_doc.pdf",
        "context": "",
        "page": 1,
    }
    non_target_passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=0,
        text="Off-target summary unrelated to requested document.",
        summary="Off-target summary unrelated to requested document.",
        metrics=[non_target_metric],
        chunk_type="body",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence(
        [non_target_passage],
        query="In the target paper, what are the CRISPR off-target rates?",
        target_doc_ids=["target_doc"],
    )
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(
        bundle,
        title="Test",
        query="In the target paper, what are the CRISPR off-target rates?",
    )
    assert structured.audit.render_status == "insufficient_evidence"
    assert not structured.supported_claims
    assert not structured.metric_summaries
    assert any("withholding off-target supported claims" in note.description for note in structured.limitations)


def test_scoped_non_metric_prefers_target_passage_claims_when_available():
    non_target_passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=0,
        text="Non-target background statement.",
        summary="Non-target background statement.",
        metrics=[],
        chunk_type="body",
        doc_type="paper",
    )
    target_passage = Passage(
        doc_id="target_doc",
        source_path="target_doc.pdf",
        page=1,
        chunk_id=1,
        text="Target document evidence about improved consistency of curation.",
        summary="Target document evidence about improved consistency of curation.",
        metrics=[],
        chunk_type="body",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence(
        [non_target_passage, target_passage],
        query="What evidence supports improved consistency?",
        target_doc_ids=["target_doc"],
    )
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(
        bundle,
        title="Test",
        query="What evidence supports improved consistency?",
    )
    assert structured.supported_claims
    assert structured.supported_claims[0].citations[0].doc_id == "target_doc"
    assert structured.audit.render_status != "off_target_evidence"


def test_scoped_non_metric_absent_target_does_not_fake_target_support():
    non_target_passage = Passage(
        doc_id="other_doc",
        source_path="other_doc.pdf",
        page=1,
        chunk_id=0,
        text="Only non-target evidence is available here.",
        summary="Only non-target evidence is available here.",
        metrics=[],
        chunk_type="body",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence(
        [non_target_passage],
        query="Does the target paper show improved consistency?",
        target_doc_ids=["target_doc"],
    )
    synthesizer = StructuredPaperSynthesizer()
    structured = synthesizer.build(
        bundle,
        title="Test",
        query="Does the target paper show improved consistency?",
    )
    claim_doc_ids = {
        citation.doc_id for claim in structured.supported_claims for citation in claim.citations if citation.doc_id
    }
    assert "target_doc" not in claim_doc_ids
    assert structured.audit.render_status in {"off_target_evidence", "insufficient_evidence"}

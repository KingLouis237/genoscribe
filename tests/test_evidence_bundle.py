from __future__ import annotations

from genoscribe.reasoning.evidence_bundle import assemble_paper_evidence
from genoscribe.schemas.document import Passage


def test_assemble_paper_evidence_tracks_missing_terms_and_metrics():
    metric = {
        "label": "AUPR",
        "value": "0.91",
        "model": "NT",
        "dataset": "Benchmark",
        "task": "PR-AUC",
        "chunk_id": 0,
        "source_doc_id": "doc1",
        "source_path": "doc1.pdf",
        "context": "AUPR comparison",
        "page": 2,
    }
    passage = Passage(
        doc_id="doc1",
        source_path="doc1.pdf",
        page=2,
        chunk_id=0,
        text="Foundation model pathogenicity benchmark comparison showing higher AUPR.",
        raw_text="",
        summary="foundation model benchmark results",
        is_table_or_figure=True,
        metrics=[metric],
        chunk_type="caption",
        doc_type="paper",
    )
    bundle = assemble_paper_evidence([passage], query="foundation model pathogenicity histograms")
    assert bundle.metrics
    candidate = bundle.metrics[0]
    assert candidate.chunk_type == "caption"
    assert candidate.context == "AUPR comparison"
    assert candidate.source_doc_id == "doc1"
    assert "foundation" not in bundle.coverage.missing_terms
    assert "pathogenicity" not in bundle.coverage.missing_terms
    assert "histograms" in bundle.coverage.missing_terms

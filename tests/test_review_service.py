from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, List

from genoscribe.app import review_service as rs
from genoscribe.app.review_service import EvidenceReviewService
from genoscribe.modes.paper_mode import PaperMode
from genoscribe.reasoning.structured_synthesizer import PaperStructuredRenderer
from genoscribe.indexing import DocumentIndex
from genoscribe.retrieval_hybrid import FilterDecision
from genoscribe.schemas.document import Passage


def _dummy_decision(passage: Passage) -> FilterDecision:
    return FilterDecision(
        passage=passage,
        fused_score=0.75,
        mode_boost=1.0,
        noise_penalty=0.1,
        query_overlap=1.0,
        informative_overlap=1.0,
        query_weight=1.0,
        duplicate_of=None,
        figure_quota_hit=False,
        kept=True,
        final_rank=1,
        chunk_type=passage.chunk_type,
        doc_type=passage.doc_type,
        reason="kept",
    )


def _build_service(monkeypatch, passages: List[Passage], tmp_path) -> EvidenceReviewService:
    service = EvidenceReviewService.__new__(EvidenceReviewService)  # type: ignore[call-arg]
    service.top_k = 2
    service.library = [
        DocumentIndex(
            doc_id="doc1",
            source_path="doc1.pdf",
            ext=".pdf",
            title="Doc 1",
            passages=passages,
            vectors=[],
            term_counts=[{} for _ in passages],
            doc_lengths=[len(p.text or "") for p in passages],
            doc_type="paper",
        )
    ]
    service.stats = SimpleNamespace(total_docs=1, avg_doc_length=1, idf_weights={})
    service.retriever = SimpleNamespace(cache_stats=lambda: {"hits": 0, "misses": 0, "size": 0})
    service.reranker = object()
    service.registry = object()
    service.query_rewriter = SimpleNamespace(rewrite=lambda q, m: q)
    service.paper_mode = PaperMode()
    service.paper_renderer = PaperStructuredRenderer()
    monkeypatch.setattr(rs, "OUTPUT_DIR", tmp_path)
    return service


def test_review_service_builds_candidate_and_metrics(monkeypatch, tmp_path):
    passage = Passage(
        doc_id="doc1",
        source_path="doc1.pdf",
        page=1,
        chunk_id=0,
        text="Model A achieved AUPR 0.85 on dataset CM.",
        summary="Model A AUPR 0.85 on CM",
        metrics=[
            {
                "label": "AUPR",
                "value": "0.85",
                "model": "Model A",
                "dataset": "CM",
                "task": "classification",
                "chunk_id": 0,
                "chunk_type": "body",
                "source_doc_id": "doc1",
                "source_path": "doc1.pdf",
            }
        ],
        chunk_type="body",
        doc_type="paper",
    )
    decision = _dummy_decision(passage)

    def fake_collect(**kwargs):
        return [passage], {"dense_ms": 1.0}, {"primary": [passage]}, [decision]

    monkeypatch.setattr(rs, "hybrid_collect", fake_collect)
    service = _build_service(monkeypatch, [passage], tmp_path)

    result = service.run_query(query="AUPR", mode="paper")

    assert result.candidates and result.candidates[0].doc_id == "doc1"
    assert result.metrics and result.metrics[0].label == "AUPR"
    assert result.bundle_preview.coverage_counts["total_passages"] == 1
    assert result.structured_answer.mode == "paper"
    assert "dense_ms" in result.diagnostics.timings_ms


def test_review_service_handles_variant_mode(monkeypatch, tmp_path):
    passage = Passage(
        doc_id="doc2",
        source_path="doc2.pdf",
        page=2,
        chunk_id=1,
        text="Variant c.123A>T classified as pathogenic in ClinVar.",
        summary="ClinVar pathogenic variant c.123A>T",
        chunk_type="body",
        doc_type="variant",
    )
    decision = _dummy_decision(passage)

    def fake_collect(**kwargs):
        return [passage], {"dense_ms": 1.0}, {"primary": [passage]}, [decision]

    monkeypatch.setattr(rs, "hybrid_collect", fake_collect)
    service = _build_service(monkeypatch, [passage], tmp_path)

    result = service.run_query(query="variant", mode="variant")

    assert result.bundle_preview.bundle_type == "variant"
    assert result.structured_answer.mode == "variant"
    assert "Variant-mode structured rendering" in result.structured_answer.rendered_text


def test_run_query_uses_target_override_when_provided(monkeypatch, tmp_path):
    passage = Passage(
        doc_id="doc1",
        source_path="doc1.pdf",
        page=1,
        chunk_id=0,
        text="AUPR 0.85",
        summary="AUPR 0.85",
        chunk_type="body",
        doc_type="paper",
    )
    decision = _dummy_decision(passage)
    captured: Dict[str, List[str]] = {}

    def fake_collect(**kwargs):
        captured["target_doc_ids"] = list(kwargs.get("target_doc_ids") or [])
        return [passage], {"dense_ms": 1.0}, {"primary": [passage]}, [decision]

    monkeypatch.setattr(rs, "hybrid_collect", fake_collect)
    monkeypatch.setattr(rs, "infer_target_doc_ids", lambda query, library: ["inferred_doc"])
    service = _build_service(monkeypatch, [passage], tmp_path)

    result = service.run_query(query="this paper", mode="paper", target_doc_ids_override=["doc1"])

    assert captured["target_doc_ids"] == ["doc1"]
    assert result.target_doc_ids == ["doc1"]


def test_run_query_falls_back_to_inference_without_override(monkeypatch, tmp_path):
    passage = Passage(
        doc_id="doc1",
        source_path="doc1.pdf",
        page=1,
        chunk_id=0,
        text="AUPR 0.85",
        summary="AUPR 0.85",
        chunk_type="body",
        doc_type="paper",
    )
    decision = _dummy_decision(passage)
    captured: Dict[str, List[str]] = {}

    def fake_collect(**kwargs):
        captured["target_doc_ids"] = list(kwargs.get("target_doc_ids") or [])
        return [passage], {"dense_ms": 1.0}, {"primary": [passage]}, [decision]

    monkeypatch.setattr(rs, "hybrid_collect", fake_collect)
    monkeypatch.setattr(rs, "infer_target_doc_ids", lambda query, library: ["doc1"])
    service = _build_service(monkeypatch, [passage], tmp_path)

    result = service.run_query(query="RNA-seq best practices paper", mode="paper")

    assert captured["target_doc_ids"] == ["doc1"]
    assert result.target_doc_ids == ["doc1"]

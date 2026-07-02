from __future__ import annotations

from genoscribe.retrieval_hybrid import hybrid_collect
from genoscribe.schemas.document import DocumentIndex, Passage
from genoscribe.search.backends import SearchBackendRegistry


def _make_passage(
    *,
    doc_id: str,
    chunk_id: int,
    text: str,
    chunk_type: str = "body",
    is_table_or_figure: bool = False,
    metrics: list | None = None,
    doc_type: str = "paper",
    noise_level: float = 0.0,
) -> Passage:
    return Passage(
        doc_id=doc_id,
        source_path=f"{doc_id}.pdf",
        page=1,
        chunk_id=chunk_id,
        text=text,
        raw_text=text,
        summary=text,
        chunk_type=chunk_type,
        doc_type=doc_type,
        is_table_or_figure=is_table_or_figure,
        metrics=metrics or [],
        noise_level=noise_level,
    )


def _make_doc(doc_id: str, title: str, passages: list[Passage]) -> DocumentIndex:
    return DocumentIndex(
        doc_id=doc_id,
        source_path=f"{doc_id}.pdf",
        ext=".pdf",
        title=title,
        passages=passages,
        vectors=[],
        term_counts=[],
        doc_lengths=[],
        doc_type="paper",
    )


class _DenseStub:
    def __init__(self, hits: list[Passage]) -> None:
        self._hits = hits

    def search(self, query: str, top_k: int = 6, timings=None):
        if timings is not None:
            timings["dense_total_ms"] = 0.0
        return [(p, 0.9) for p in self._hits[:top_k]]


class _RerankerStub:
    def rerank(self, passages: list[Passage], query: str, top_k: int | None = None):
        limit = top_k or len(passages)
        return [(p, 1.0 - (idx * 0.01)) for idx, p in enumerate(passages[:limit])]


def test_scoped_target_seed_injected_when_upstream_has_no_target(monkeypatch):
    target = _make_passage(doc_id="target_doc", chunk_id=1, text="plos genetics evidence claims summary")
    non_target = _make_passage(doc_id="other_doc", chunk_id=2, text="generic background discussion")
    library = [
        _make_doc("target_doc", "PLOS target", [target]),
        _make_doc("other_doc", "Other", [non_target]),
    ]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In PLOS paper summarize evidence claims",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([non_target]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    assert "target_seed" in stage_hits
    assert stage_hits["target_seed"]
    assert all(p.doc_id == "target_doc" for p in stage_hits["target_seed"])


def test_scoped_target_seed_not_added_when_target_already_upstream(monkeypatch):
    target = _make_passage(doc_id="target_doc", chunk_id=1, text="plos genetics evidence claims summary")
    library = [_make_doc("target_doc", "PLOS target", [target])]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In PLOS paper summarize evidence claims",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    assert "target_seed" not in stage_hits


def test_scoped_target_seed_not_used_outside_paper_mode(monkeypatch):
    target = _make_passage(doc_id="target_doc", chunk_id=1, text="plos genetics evidence claims summary")
    non_target = _make_passage(doc_id="other_doc", chunk_id=2, text="generic background discussion")
    library = [
        _make_doc("target_doc", "PLOS target", [target]),
        _make_doc("other_doc", "Other", [non_target]),
    ]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In PLOS paper summarize evidence claims",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([non_target]),
        reranker=_RerankerStub(),
        mode="variant",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    assert "target_seed" not in stage_hits


def test_scoped_target_seed_rejects_low_quality_figure_junk(monkeypatch):
    bad_figure = _make_passage(
        doc_id="target_doc",
        chunk_id=1,
        text="plos figure 0 1 2 axis ticks",
        chunk_type="caption",
        is_table_or_figure=True,
        metrics=[],
    )
    good_body = _make_passage(
        doc_id="target_doc",
        chunk_id=2,
        text="plos genetics evidence claims summary and limitations",
    )
    non_target = _make_passage(doc_id="other_doc", chunk_id=3, text="generic background discussion")
    library = [
        _make_doc("target_doc", "PLOS target", [bad_figure, good_body]),
        _make_doc("other_doc", "Other", [non_target]),
    ]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In PLOS paper summarize evidence claims and limitations",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([non_target]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    seeded = stage_hits.get("target_seed", [])
    assert seeded
    assert all(p.chunk_id != 1 for p in seeded)
    assert any(p.chunk_id == 2 for p in seeded)


def test_scoped_target_seed_slice_is_small_and_doc_diverse(monkeypatch):
    target_a_1 = _make_passage(doc_id="target_a", chunk_id=1, text="plos genetics evidence claims summary")
    target_a_2 = _make_passage(doc_id="target_a", chunk_id=2, text="plos genetics evidence limitations")
    target_b_1 = _make_passage(doc_id="target_b", chunk_id=3, text="plos genetics evidence support details")
    non_target = _make_passage(doc_id="other_doc", chunk_id=4, text="generic background discussion")
    library = [
        _make_doc("target_a", "Target A", [target_a_1, target_a_2]),
        _make_doc("target_b", "Target B", [target_b_1]),
        _make_doc("other_doc", "Other", [non_target]),
    ]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In PLOS paper summarize evidence claims",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([non_target]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=6,
        target_doc_ids=["target_a", "target_b"],
    )
    seeded = stage_hits.get("target_seed", [])
    assert 1 <= len(seeded) <= 2
    assert len({p.doc_id for p in seeded}) == len(seeded)


def test_scoped_target_seed_allows_target_doc_type_mismatch_with_penalty(monkeypatch):
    variant_typed_target = _make_passage(
        doc_id="target_doc",
        chunk_id=1,
        text="plos genetics evidence claims summary",
        doc_type="variant",
    )
    non_target = _make_passage(doc_id="other_doc", chunk_id=2, text="generic background discussion")
    library = [
        _make_doc("target_doc", "PLOS target", [variant_typed_target]),
        _make_doc("other_doc", "Other", [non_target]),
    ]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In PLOS paper summarize evidence claims",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([non_target]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    seeded = stage_hits.get("target_seed", [])
    assert seeded
    assert seeded[0].doc_id == "target_doc"


def test_scoped_metric_target_seed_injected_when_upstream_misses_metric_chunks(monkeypatch):
    target_non_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=1,
        text="benchmark methods and model-system discussion",
        metrics=[],
    )
    target_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=2,
        text="benchmark model performance with accuracy and recall metrics",
        metrics=[{"label": "Accuracy", "value": "0.91", "task": "classification"}],
    )
    non_target = _make_passage(doc_id="other_doc", chunk_id=3, text="benchmark model discussion")
    library = [
        _make_doc("target_doc", "Target paper", [target_non_metric, target_metric]),
        _make_doc("other_doc", "Other", [non_target]),
    ]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In the target paper, extract benchmark metrics and model-system labels",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target_non_metric, non_target]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    seeded = stage_hits.get("target_metric_seed", [])
    assert len(seeded) == 1
    assert seeded[0].doc_id == "target_doc"
    assert seeded[0].chunk_id == 2
    assert any(p.doc_id == "target_doc" and p.chunk_id == 2 for p in stage_hits["reranked"])


def test_scoped_metric_target_seed_rejects_noisy_or_front_matter_chunks(monkeypatch):
    target_non_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=1,
        text="benchmark methods and model-system discussion",
        metrics=[],
    )
    front_matter_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=2,
        text="BMC Genomics (2025) Open Access https://doi.org/10.1186/s12864-025-11741-4",
        chunk_type="caption",
        is_table_or_figure=True,
        metrics=[{"label": "Accuracy", "value": "0.92", "task": "classification"}],
    )
    noisy_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=3,
        text="benchmark metrics precision recall",
        metrics=[{"label": "Recall", "value": "0.88", "task": "classification"}],
        noise_level=0.95,
    )
    library = [_make_doc("target_doc", "Target paper", [target_non_metric, front_matter_metric, noisy_metric])]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In the target paper, extract benchmark metrics and model-system labels",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target_non_metric]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    assert not stage_hits.get("target_metric_seed")


def test_scoped_metric_target_seed_does_not_inject_non_target_chunks(monkeypatch):
    target_non_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=1,
        text="benchmark methods and model-system discussion",
        metrics=[],
    )
    non_target_metric = _make_passage(
        doc_id="other_doc",
        chunk_id=2,
        text="benchmark model performance with accuracy and recall metrics",
        metrics=[{"label": "Accuracy", "value": "0.91", "task": "classification"}],
    )
    library = [
        _make_doc("target_doc", "Target paper", [target_non_metric]),
        _make_doc("other_doc", "Other", [non_target_metric]),
    ]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In the target paper, extract benchmark metrics and model-system labels",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target_non_metric, non_target_metric]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    assert not stage_hits.get("target_metric_seed")


def test_scoped_metric_target_seed_does_not_run_for_unscoped_or_non_metric_queries(monkeypatch):
    target_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=2,
        text="benchmark model performance with accuracy and recall metrics",
        metrics=[{"label": "Accuracy", "value": "0.91", "task": "classification"}],
    )
    target_non_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=1,
        text="benchmark methods and model-system discussion",
        metrics=[],
    )
    library = [_make_doc("target_doc", "Target paper", [target_non_metric, target_metric])]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits_unscoped = hybrid_collect(
        library=library,
        stats=None,
        query="Extract benchmark metrics and model-system labels",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target_non_metric]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=[],
    )
    assert "target_metric_seed" not in stage_hits_unscoped

    _, _, stage_hits_non_metric = hybrid_collect(
        library=library,
        stats=None,
        query="In the target paper, summarize limitations and caveats",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target_non_metric]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    assert "target_metric_seed" not in stage_hits_non_metric


def test_scoped_metric_target_seed_respects_cap(monkeypatch):
    target_non_metric = _make_passage(
        doc_id="target_doc",
        chunk_id=1,
        text="benchmark methods and model-system discussion",
        metrics=[],
    )
    metric_chunks = [
        _make_passage(
            doc_id="target_doc",
            chunk_id=idx,
            text=f"benchmark model metric chunk {idx} with accuracy recall",
            metrics=[{"label": "Accuracy", "value": f"0.9{idx}", "task": "classification"}],
        )
        for idx in (2, 3, 4)
    ]
    library = [_make_doc("target_doc", "Target paper", [target_non_metric, *metric_chunks])]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In the target paper, extract benchmark metrics and model-system labels",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target_non_metric]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["target_doc"],
    )
    seeded = stage_hits.get("target_metric_seed", [])
    assert 1 <= len(seeded) <= 2


def test_scoped_metric_target_seed_not_added_when_upstream_already_has_target_metric(monkeypatch):
    target_metric = _make_passage(
        doc_id="plos_doc",
        chunk_id=8,
        text="target paper benchmark model metrics with AUC and AUPR",
        metrics=[{"label": "AUPR", "value": "0.87", "task": "pr-auc"}],
        chunk_type="body",
    )
    target_non_metric = _make_passage(
        doc_id="plos_doc",
        chunk_id=9,
        text="target paper methods section",
        metrics=[],
    )
    library = [_make_doc("plos_doc", "PLOS target", [target_metric, target_non_metric])]

    monkeypatch.setattr(
        "genoscribe.retrieval_hybrid.filter_passages_for_quality",
        lambda scored, top_k, **_: ([p for p, _ in scored[:top_k]], []),
    )

    _, _, stage_hits = hybrid_collect(
        library=library,
        stats=None,
        query="In the PLOS paper, extract explicitly reported benchmark metrics",
        search_method="bm25",
        search_registry=SearchBackendRegistry(),
        dense_retriever=_DenseStub([target_metric, target_non_metric]),
        reranker=_RerankerStub(),
        mode="paper",
        top_k=4,
        target_doc_ids=["plos_doc"],
    )
    assert "target_metric_seed" not in stage_hits

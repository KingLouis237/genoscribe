from __future__ import annotations

from genoscribe.retrieval_hybrid import filter_passages_for_quality
from genoscribe.schemas.document import Passage


def _make_passage(
    *,
    doc_id: str = "doc",
    chunk_id: int = 0,
    text: str,
    chunk_type: str = "caption",
    doc_type: str = "variant",
    metrics: list | None = None,
    is_table_or_figure: bool = True,
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
        noise_level=noise_level,
        is_table_or_figure=is_table_or_figure,
        metrics=metrics or [],
        chunk_type=chunk_type,
        doc_type=doc_type,
    )


def test_paper_mode_drops_variant_figure_without_overlap():
    metrics = [
        {
            "label": "AUPR",
            "value": "0.87",
            "model": "DYNA",
            "dataset": "Unknown",
            "task": "PR-AUC",
            "context": "",
            "panel": "",
            "page": 1,
        }
    ]
    passage = _make_passage(
        doc_id="variant_doc",
        text="AUPR performance summary with no mention of the query focus text.",
        metrics=metrics,
    )
    filtered, decisions = filter_passages_for_quality(
        [(passage, 0.5)],
        top_k=3,
        mode="paper",
        query_terms=["foundation", "model", "pathogenicity", "benchmarks"],
    )
    assert not filtered
    assert decisions[0].reason.startswith("dropped: figure")


def test_paper_mode_keeps_query_relevant_figure_with_metrics():
    metrics = [
        {
            "label": "AUPR",
            "value": "0.91",
            "model": "NT",
            "dataset": "Benchmark",
            "task": "PR-AUC",
            "context": "",
            "panel": "",
            "page": 2,
        }
    ]
    passage = _make_passage(
        doc_id="paper_doc",
        text="Foundation model pathogenicity benchmark AUPR comparison figure.",
        doc_type="paper",
        metrics=metrics,
    )
    filtered, decisions = filter_passages_for_quality(
        [(passage, 0.5)],
        top_k=3,
        mode="paper",
        query_terms=["foundation", "model", "pathogenicity", "benchmarks"],
    )
    assert filtered == [passage]
    assert decisions[0].kept


def test_target_doc_bias_prefers_named_document():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="DYNA pathogenicity discussion",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    other = _make_passage(
        doc_id="king_doc",
        chunk_id=1,
        text="General pathogenicity discussion",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    filtered, _ = filter_passages_for_quality(
        [(target, 0.35), (other, 0.65)],
        top_k=1,
        mode="paper",
        query_terms=["pathogenicity"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == [target]


def test_target_doc_bias_still_drops_low_quality_passages():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="Completely unrelated content",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    other = _make_passage(
        doc_id="king_doc",
        chunk_id=1,
        text="Pathogenicity benchmarking discussion with details.",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    filtered, decisions = filter_passages_for_quality(
        [(target, 0.8), (other, 0.5)],
        top_k=1,
        mode="paper",
        query_terms=["pathogenicity"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == [other]
    target_decision = next(dec for dec in decisions if dec.passage.doc_id == "dyna_doc")
    assert target_decision.reason.startswith("dropped")


def test_target_figure_without_metrics_requires_relevance():
    relevant = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="DYNA pathogenicity violin plot overview",
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
    )
    noisy = _make_passage(
        doc_id="dyna_doc",
        chunk_id=1,
        text="0 5 10 15 axis label grid",
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
    )
    non_target = _make_passage(
        doc_id="other_doc",
        chunk_id=2,
        text="pathogenicity violin plot overview",
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
    )
    filtered, _ = filter_passages_for_quality(
        [(relevant, 0.4), (noisy, 0.6), (non_target, 0.5)],
        top_k=3,
        mode="paper",
        query_terms=["pathogenicity"],
        target_doc_ids=["dyna_doc"],
    )
    assert relevant in filtered
    assert noisy not in filtered
    assert non_target not in filtered


def test_metric_intent_rescues_metric_bearing_passage():
    non_metric = _make_passage(
        doc_id="paper_doc",
        chunk_id=0,
        text="Benchmark discussion without explicit numeric metric extraction fields.",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
        metrics=[],
    )
    metric = _make_passage(
        doc_id="paper_doc",
        chunk_id=1,
        text="AUPR 0.91 and AUROC 0.95 are reported for the evaluated model.",
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
        metrics=[
            {
                "label": "AUPR",
                "value": "0.91",
                "model": "ModelX",
                "dataset": "Benchmark",
                "task": "PR-AUC",
                "context": "",
                "panel": "",
                "page": 1,
            }
        ],
    )
    filtered, decisions = filter_passages_for_quality(
        [(non_metric, 0.9), (metric, 0.6)],
        top_k=1,
        mode="paper",
        query_terms=["aupr", "precision", "recall", "metrics"],
    )
    assert filtered == [metric]
    metric_decision = next(dec for dec in decisions if dec.passage.chunk_id == 1)
    assert metric_decision.kept is True
    assert "dropped: no informative-term overlap" not in metric_decision.reason


def test_scoped_target_survives_without_informative_overlap_when_quality_qualified():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="dyna benchmarking discussion",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    filtered, decisions = filter_passages_for_quality(
        [(target, 0.3)],
        top_k=1,
        mode="paper",
        query_terms=["dyna", "paper", "limitations"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == [target]
    target_decision = next(dec for dec in decisions if dec.passage.doc_id == "dyna_doc")
    assert target_decision.kept is True


def test_scoped_target_still_drops_when_overlap_is_too_weak():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="dyna benchmarking discussion",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    filtered, decisions = filter_passages_for_quality(
        [(target, 0.3)],
        top_k=1,
        mode="paper",
        query_terms=["dyna", "paper", "limitations", "conflicts", "caveats"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == []
    target_decision = next(dec for dec in decisions if dec.passage.doc_id == "dyna_doc")
    assert target_decision.reason.startswith("dropped")


def test_non_target_still_drops_without_informative_overlap():
    non_target = _make_passage(
        doc_id="king_doc",
        chunk_id=1,
        text="dyna benchmarking discussion",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    filtered, decisions = filter_passages_for_quality(
        [(non_target, 0.3)],
        top_k=1,
        mode="paper",
        query_terms=["dyna", "paper", "limitations"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == []
    decision = decisions[0]
    assert decision.reason == "dropped: no informative-term overlap"


def test_target_anchor_replacement_is_bounded_by_score_margin():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="dyna benchmarking discussion",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    strong_non_target = _make_passage(
        doc_id="king_doc",
        chunk_id=1,
        text="paper limitations analysis",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    filtered, _ = filter_passages_for_quality(
        [(strong_non_target, 0.5), (target, 0.32)],
        top_k=1,
        mode="paper",
        query_terms=["dyna", "paper", "limitations"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == [target]

    far_weaker_target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=2,
        text="dyna benchmarking discussion",
        chunk_type="body",
        doc_type="paper",
        is_table_or_figure=False,
    )
    filtered_weak, _ = filter_passages_for_quality(
        [(strong_non_target, 0.7), (far_weaker_target, 0.18)],
        top_k=1,
        mode="paper",
        query_terms=["dyna", "paper", "limitations"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered_weak == [strong_non_target]


def test_scoped_metric_intent_target_runtime_metric_signal_survives():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="AUPR = 0.91 and AUROC = 0.95 metrics for the target benchmark.",
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
        metrics=[],
    )
    filtered, decisions = filter_passages_for_quality(
        [(target, 0.42)],
        top_k=1,
        mode="paper",
        query_terms=["aupr", "metrics"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == [target]
    assert decisions[0].kept is True


def test_scoped_metric_intent_runtime_signal_does_not_rescue_weak_or_noisy_target():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text="AUPR = 0.91 2026 2027 2028 2029 2030 2031 2032 2033",
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
        metrics=[],
        noise_level=0.7,
    )
    filtered, decisions = filter_passages_for_quality(
        [(target, 0.42)],
        top_k=1,
        mode="paper",
        query_terms=["aupr", "precision", "recall", "metrics"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == []
    assert decisions[0].reason.startswith("dropped")


def test_scoped_metric_intent_runtime_signal_does_not_rescue_non_target():
    non_target = _make_passage(
        doc_id="king_doc",
        chunk_id=0,
        text="AUPR = 0.91 and AUROC = 0.95 metrics for a benchmark figure.",
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
        metrics=[],
    )
    filtered, decisions = filter_passages_for_quality(
        [(non_target, 0.42)],
        top_k=1,
        mode="paper",
        query_terms=["aupr", "metrics"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == []
    assert decisions[0].reason == "dropped: figure lacks structured metrics"


def test_scoped_metric_intent_runtime_signal_ignores_doi_year_page_noise():
    target = _make_passage(
        doc_id="dyna_doc",
        chunk_id=0,
        text=(
            "Metrics appendix page 12, pages 101-110, 2021 release, "
            "DOI 10.1371/journal.pgen.1011540, volume 12 issue 3."
        ),
        chunk_type="caption",
        doc_type="paper",
        is_table_or_figure=True,
        metrics=[],
    )
    filtered, decisions = filter_passages_for_quality(
        [(target, 0.42)],
        top_k=1,
        mode="paper",
        query_terms=["metrics", "precision"],
        target_doc_ids=["dyna_doc"],
    )
    assert filtered == []
    assert decisions[0].reason == "dropped: figure lacks structured metrics"


def test_scoped_target_metric_figure_survives_when_quality_qualified():
    target_metric = _make_passage(
        doc_id="plos_doc",
        chunk_id=0,
        text="AUC and precision results for the target paper comparison figure.",
        chunk_type="caption",
        doc_type="variant",
        is_table_or_figure=True,
        metrics=[
            {
                "label": "AUC",
                "value": "0.87",
                "model": "TargetModel",
                "dataset": "TargetDataset",
                "task": "ROC-AUC",
                "context": "",
                "panel": "",
                "page": 1,
            }
        ],
    )
    filtered, decisions = filter_passages_for_quality(
        [(target_metric, 0.35)],
        top_k=1,
        mode="paper",
        query_terms=["auc", "precision", "recall", "oddsratio", "pvalues", "metrics"],
        target_doc_ids=["plos_doc"],
    )
    assert filtered == [target_metric]
    assert decisions[0].kept is True


def test_scoped_target_metric_figure_still_drops_when_noise_too_high():
    target_metric = _make_passage(
        doc_id="plos_doc",
        chunk_id=0,
        text="AUC and precision results for the target paper comparison figure.",
        chunk_type="caption",
        doc_type="variant",
        is_table_or_figure=True,
        noise_level=0.6,
        metrics=[
            {
                "label": "AUC",
                "value": "0.87",
                "model": "TargetModel",
                "dataset": "TargetDataset",
                "task": "ROC-AUC",
                "context": "",
                "panel": "",
                "page": 1,
            }
        ],
    )
    filtered, decisions = filter_passages_for_quality(
        [(target_metric, 0.35)],
        top_k=1,
        mode="paper",
        query_terms=["auc", "precision", "recall", "oddsratio", "pvalues", "metrics"],
        target_doc_ids=["plos_doc"],
    )
    assert filtered == []
    assert decisions[0].reason == "dropped: figure lacks informative overlap"


def test_scoped_target_metric_override_does_not_apply_to_non_target_passages():
    non_target_metric = _make_passage(
        doc_id="other_doc",
        chunk_id=0,
        text="AUC and precision results for a non-target figure.",
        chunk_type="caption",
        doc_type="variant",
        is_table_or_figure=True,
        metrics=[
            {
                "label": "AUC",
                "value": "0.87",
                "model": "OtherModel",
                "dataset": "OtherDataset",
                "task": "ROC-AUC",
                "context": "",
                "panel": "",
                "page": 1,
            }
        ],
    )
    filtered, decisions = filter_passages_for_quality(
        [(non_target_metric, 0.35)],
        top_k=1,
        mode="paper",
        query_terms=["auc", "precision", "recall", "oddsratio", "pvalues", "metrics"],
        target_doc_ids=["plos_doc"],
    )
    assert filtered == []
    assert decisions[0].reason == "dropped: figure lacks informative overlap"


def test_metric_intent_target_metric_override_does_not_apply_when_unscoped():
    target_like_metric = _make_passage(
        doc_id="plos_doc",
        chunk_id=0,
        text="AUC and precision results for the target paper comparison figure.",
        chunk_type="caption",
        doc_type="variant",
        is_table_or_figure=True,
        metrics=[
            {
                "label": "AUC",
                "value": "0.87",
                "model": "TargetModel",
                "dataset": "TargetDataset",
                "task": "ROC-AUC",
                "context": "",
                "panel": "",
                "page": 1,
            }
        ],
    )
    filtered, decisions = filter_passages_for_quality(
        [(target_like_metric, 0.35)],
        top_k=1,
        mode="paper",
        query_terms=["auc", "precision", "recall", "oddsratio", "pvalues", "metrics"],
        target_doc_ids=[],
    )
    assert filtered == []
    assert decisions[0].reason == "dropped: figure lacks informative overlap"

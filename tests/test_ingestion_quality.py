from __future__ import annotations

from genoscribe.ingestion.chunk_typing import classify_chunk
from genoscribe.ingestion.metric_extractor import extract_metrics
from genoscribe.ingestion.table_figure_extractor import strip_figure_noise


def test_strip_figure_noise_removes_numeric_axes():
    raw = "0 5 10 15 20\nPLLR\np = 0.05\nDistribution of PLLR"
    cleaned, noise = strip_figure_noise(raw, True)
    assert "0 5 10" not in cleaned
    assert "Distribution" in cleaned
    assert noise > 0.3


def test_extract_metrics_parses_values():
    text = "AUPR: 0.87 Baseline AUPR = 0.51\np = 7.0e-3"
    metrics = extract_metrics(text)
    labels = {m["label"]: m["value"] for m in metrics}
    assert "AUPR" in labels and labels["AUPR"] == "0.87"
    assert "p-value" in labels and labels["p-value"] == "7.0e-3"


def test_extract_metrics_prefers_label_for_model():
    text = "DYNA KL Divergence: 13.2859 CART RF BART XGBoost AdaBoost"
    metrics = extract_metrics(text)
    match = next(m for m in metrics if m["label"].startswith("DYNA"))
    assert match["model"] == "DYNA"


def test_extract_metrics_detects_dataset_from_context():
    text = "DYNA KL Divergence: 24.6582 ClinVar CM Genes were used in this panel"
    metrics = extract_metrics(text)
    match = next(m for m in metrics if m["label"].startswith("DYNA"))
    assert match["dataset"] == "ClinVar CM"


def test_extract_metrics_rejects_doi_like_labels():
    text = "https://doi.org/10.1000/xyz: 0.75"
    metrics = extract_metrics(text)
    assert metrics == []


def test_extract_metrics_assigns_unknowns_when_ambiguous():
    text = "Accuracy: 0.91"
    metrics = extract_metrics(text)
    assert metrics
    assert metrics[0]["model"] == "Unknown"
    assert metrics[0]["dataset"] == "Unknown"


def test_extract_metrics_detects_shine_dataset():
    text = "BUSCO completeness: 95.1% on SHINE benchmark assemblies"
    metrics = extract_metrics(text)
    assert metrics
    assert metrics[0]["dataset"] == "SHINE benchmark"


def test_extract_metrics_rejects_two_letter_label():
    text = "of SS: 0.92"
    metrics = extract_metrics(text)
    assert metrics == []


def test_extract_metrics_keeps_allowed_short_label():
    text = "AUC: 0.81"
    metrics = extract_metrics(text)
    assert metrics
    assert metrics[0]["label"] == "AUC"


def test_extract_metrics_detects_varcopp_dataset():
    text = (
        "The VarCoPP support of SS = 46.2 and SS = 24 indicates strong evidence. "
        "VarCoPP remains cautious when annotations are missing."
    )
    metrics = extract_metrics(text)
    assert metrics
    assert all(m["model"] == "VarCoPP" for m in metrics)
    assert all(m["dataset"] == "VarCoPP cohort" for m in metrics)
    assert any("VarCoPP SS" in m["label"] for m in metrics)


def test_extract_metrics_detects_varcopp_classification_score():
    text = "VarCoPP classification score CS = 0.64 remains a strong discriminator."
    metrics = extract_metrics(text)
    assert any(m["task"] == "Classification Score" for m in metrics)


def test_extract_metrics_detects_varcopp_confidence_zone():
    text = "The 95% confidence zone requires CS >= 0.55 and SS >= 75 for VarCoPP predictions."
    metrics = extract_metrics(text)
    assert any("95% zone" in m["label"] for m in metrics)


def test_extract_metrics_extracts_shine_balanced_accuracy():
    text = (
        "SHINE provides balanced accuracy scores of 0.777 and 0.699 for deletions and insertions. "
        "SHINE with an AUC value of 0.877 is significantly better than baselines."
    )
    metrics = extract_metrics(text)
    labels = {m["label"]: m["value"] for m in metrics}
    assert any("balanced accuracy (deletions)" in label for label in labels)
    assert any("balanced accuracy (insertions)" in label for label in labels)
    assert any(label.startswith("SHINE AUC") for label in labels)


def test_extract_metrics_parses_benchmark_table_rows():
    text = (
        "Model Accuracy Precision Recall\n"
        "HyenaDNA Tiny 56.65 66.59 43.37\n"
        "GenaLM Bert t2t 60.58 81.56 69.52\n"
        "Nucleotide Transformer 100m so 90.62 91.17 90.89\n"
    )
    metrics = extract_metrics(text)
    assert any(m["model"].startswith("HyenaDNA") and m["label"] == "Accuracy" and m["value"] == "56.65" for m in metrics)
    assert any(
        m["model"].startswith("Nucleotide Transformer")
        and m["label"] == "Recall"
        and m["value"] == "90.89"
        for m in metrics
    )


def test_extract_metrics_parses_auc_table_header_variants():
    text = (
        "Model AUC ROC AUC PR\n"
        "SNPred 0.994218 0.993159\n"
        "GenaLM Large 0.731805 0.717726\n"
    )
    metrics = extract_metrics(text)
    assert any(m["label"] == "ROC AUC" and m["value"] == "0.994218" for m in metrics)
    assert any(m["label"] == "PR AUC" and m["value"] == "0.717726" for m in metrics)


def test_extract_metrics_table_parser_ignores_integer_rows():
    text = (
        "Model Accuracy Precision Recall\n"
        "ModelA 2021 12 11\n"
        "ModelB 2019 10 9\n"
    )
    metrics = extract_metrics(text)
    assert metrics == []


def test_classify_chunk_detects_panel_caption():
    text = "a\nFigure 3. Overview of the training pipeline."
    chunk_type = classify_chunk(raw_text=text, clean_text=text, is_table_or_figure=False, noise_level=0.0)
    assert chunk_type == "caption"


def test_classify_chunk_flags_axis_heavy_as_figure():
    text = "0 5 10 15 20\n30 40 50\n60 70 80"
    chunk_type = classify_chunk(raw_text=text, clean_text=text, is_table_or_figure=False, noise_level=0.6)
    assert chunk_type == "figure_derived"

from genoscribe.app import build_summary_text, summarize_passage_text


def test_summarize_passage_skips_fragment_and_finds_sentence():
    snippet = (
        "prediction performs as well as predictions from experiments. "
        "Full sentence starts here with proper context. Another sentence follows."
    )
    summary = summarize_passage_text(snippet)
    assert summary.startswith("Full sentence starts here")


def test_build_summary_text_highlights_metrics_and_query_terms():
    summary = "EVE achieved an AUC of 0.95 on ClinVar variants."
    text_obj = build_summary_text(summary, "EVE AUC metrics")
    plain = text_obj.plain
    spans = [(span.style, plain[span.start:span.end]) for span in text_obj.spans]

    assert ("bold", "0.95") in spans
    highlighted_terms = {segment.lower() for style, segment in spans if style in {"green", "bright_magenta"}}
    assert "eve" in highlighted_terms
    assert "auc" in highlighted_terms

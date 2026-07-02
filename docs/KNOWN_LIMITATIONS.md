# Known Limitations

GenoScribe is an evidence-review workbench, not a clinical decision system or a general chatbot.

## Current validation boundary

- The flagship paper-mode validation harness currently reports 21/25 passing tasks (84%) on the fixed matrix recorded in `docs/VALIDATION_CHECKPOINT_2026-04.md`.
- Probe reports show stronger scoping behavior, but probes are not a substitute for broad external validation.
- Validation is strongest for paper-mode retrieval, scoped evidence selection, and audit-status behavior.

## Paper mode

- Metric-intent queries remain the most fragile path, especially when metrics are embedded in narrative text, noisy tables, or figure-heavy passages.
- Some scoped queries can still lose target-document evidence when candidate discovery fails upstream.
- Audit labels are conservative by design, but they are still heuristic and should be inspected with provenance.

## Assembly mode

- Assembly mode is secondary and narrow by design.
- It is intended for QC-style evidence around QUAST, BUSCO, KAT, Bandage, and related assembly diagnostics.
- It should not redefine the product or be treated as a broad genomics assistant mode.

## Variant mode

- Variant mode is experimental and research-only.
- It is not clinical interpretation support.
- HGVS normalization, ancestry/cohort extraction, contradiction tracking, and evidence completeness remain under validation.
- Outputs should be reviewed manually before any scientific or operational use.

## Corpus and generalization

- The curated corpus improves reproducibility but is still small.
- Some validation gains are heuristic and may not transfer to unfamiliar publisher layouts, OCR-heavy PDFs, supplements, or non-English documents.
- Local PDFs and generated indexes are intentionally excluded from public release; users must build their own local corpus.

## Runtime and operations

- Dense retrieval depends on local embedding/index availability and can be slow on CPU during cold starts.
- The Streamlit app is a developer inspection tool, not a polished product interface.
- The CLI requires a configured Anthropic API key for model-backed answering.

# Quickstart Demo

This demo works from a clean checkout without real PDFs, private corpus data, generated vector indexes, or committed runtime outputs.

## 1. Install dependencies

```bash
uv sync
```

## 2. Run tests

```bash
uv run pytest
```

## 3. Build the synthetic demo corpus

```bash
uv run python scripts/demo_build_sample_corpus.py
```

This ingests `docs/examples/demo_paper.md` into ignored local runtime folders under `src/genomics_assistant_data/`.

## 4. Launch the evidence review app

```bash
uv run streamlit run scripts/review_gui_streamlit.py
```

Try this paper-mode query:

```text
From the GenoScribe-Scout benchmark paper, extract AUROC and AUPRC metrics.
```

## 5. Optional demo validation

```bash
uv run python scripts/paper_validation_harness.py --matrix docs/examples/demo_validation_matrix.json --manifest docs/examples/demo_manifest.json --top-k 4
```

This validates only the synthetic demo paper. It is not the full paper-mode benchmark.

## Full curated-corpus validation

The full benchmark still requires the local curated corpus and should not be committed to Git:

```bash
uv run python scripts/corpus_sync.py --download-missing --ingest-missing
uv run python scripts/paper_validation_harness.py --top-k 4
```

## Notes

- The synthetic demo paper contains no real patient data, clinical records, or copyrighted paper text.
- Generated library files, reports, caches, and vector stores remain ignored by Git.
- Variant mode remains experimental and research-only.

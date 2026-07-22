# GenoScribe

GenoScribe started from a simple frustration: scientific papers are easy to summarize badly, but hard to review carefully.

I built this as a local evidence-review workbench for genomics papers and technical documents. The goal is not to make a chatbot that sounds confident. The goal is to make the evidence visible: what was retrieved, where it came from, what claim it supports, what is missing, and when the system should say `insufficient_evidence` instead of pretending.

Right now, the strongest workflow is paper mode. It focuses on scoped document retrieval, provenance-bearing evidence bundles, metric surfacing, structured synthesis, audit states, and reproducible validation reports.

This is a research/developer MVP. It is not a clinical tool, not a diagnostic assistant, and not a substitute for manual scientific review.

GenoScribe is a local, evidence-first review workbench for genomics papers and technical documents.

It is built to help scientists inspect evidence, not accept fluent summaries. The system retrieves passages, preserves provenance, surfaces structured evidence, and assigns explicit audit status before rendering user-facing output.

## Why this exists

A lot of AI tools can generate fluent summaries. That is not the hard part.

The hard part is knowing whether a summary is actually grounded in the paper, whether the retrieved passages are on-target, whether metrics came from the right document, and whether unsupported topics were clearly separated from supported claims.

GenoScribe is my attempt to build that trustworthy, transparent and interpretable layer first.

The project is especially shaped by bioinformatics and genomics workflows, where small errors in provenance, labels, variants, cohorts, or benchmark interpretation can completely change the meaning of a result.

## Product hierarchy

**Core / flagship: Paper mode**  
Structured paper retrieval, citation-faithful evidence review, supported/unsupported topic handling, contradiction detection, and audit-first synthesis.

**Secondary / specialized: Assembly mode**  
Narrow-scope QC interpretation around QUAST, BUSCO, KAT, Bandage, and related assembly diagnostics. Assembly mode complements the paper workflow; it does not redefine the product.

**Experimental / research-only: Variant mode**  
A research-only prototype for variant-literature evidence assembly. It remains under validation and is not production-ready or suitable for clinical interpretation.

## What GenoScribe is not

- Not a general chatbot.
- Not a clinical decision engine.
- Not a substitute for manual scientific review.
- Not a broad agent framework.

## Current validation checkpoint

Public clean-checkout validation:

- `uv sync` works from a fresh export.
- `uv run pytest`: 107 passed, 1 skipped.
- Synthetic public demo corpus builds from a clean checkout.
- Synthetic demo validation: 5/5 auto-pass.

Local curated-corpus validation:

- Fixed paper-mode benchmark: 21/25 = 84%.
- Paper-primary probe corpus and monitoring protocol are in place.
- Full curated-corpus validation requires locally synced papers and generated indexes, which are intentionally not committed to Git.

`The synthetic demo validates the public workflow only. It is not evidence of scientific or clinical performance`.

- Remaining known weaknesses are documented in [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

The current state-of-project assessment is in [docs/GENOSCRIBE_STATE_OF_PROJECT_2026-05.md](docs/GENOSCRIBE_STATE_OF_PROJECT_2026-05.md).

## Development history

GenoScribe was developed over multiple validation-driven sprints. The public repository starts from a clean release snapshot because the original working repo contained local PDFs, generated indexes, caches, reports, notebooks, and experimental artifacts that should not be published.

Public clean-checkout validation currently covers install, tests, synthetic demo corpus build, and demo validation. Full curated-corpus validation remains local because the benchmark requires synced papers that are not committed to Git.

- [Project history](docs/PROJECT_HISTORY.md)
- [Validation summary](docs/VALIDATION_SUMMARY.md)
- [Development milestones](docs/DEVELOPMENT_MILESTONES.md)
- [Engineering log](research/ENGINEERING_LOG.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)

## Core pipeline

```text
query
-> mode / target scope handling
-> hybrid retrieval
-> target-aware seeding when needed
-> dense/sparse fusion
-> reranking
-> quality filtering
-> metric surfacing
-> evidence bundle
-> structured synthesis
-> audit status
-> validation/probe report
-> monitoring
```

Metric extraction is mostly ingestion-time. Metric surfacing and claim selection happen at query time.

## Features

- Local PDF/TXT/MD indexing.
- Hybrid retrieval with BM25, dense embeddings, fusion, and reranking.
- Persistent FAISS + SQLite vector storage.
- Query embedding cache.
- Section-aware chunking with `doc_type` and `chunk_type` metadata.
- Structured metric extraction and provenance-aware evidence bundles.
- Scoped target-document inference and explicit target overrides.
- Structured paper synthesis before prose rendering.
- Audit statuses: `supported`, `partially_supported`, `insufficient_evidence`, `off_target_evidence`, `conflicting_evidence`.
- Paper-mode validation harness and probe runner.
- Local Streamlit evidence/report viewer for debugging.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) 0.5+
- Python managed through `uv`
- `ANTHROPIC_API_KEY` for model-backed CLI answering

## Install

```bash
uv sync
```

## Run the CLI

```bash
uv run genoscribe
```

On first run, GenoScribe creates local data folders under `genomics_assistant_data/`. These folders are ignored by Git.

## Add documents

Drop PDF/TXT/MD files into the local inbox:

```text
genomics_assistant_data/inbox/
```

Then run the CLI or use:

```text
inbox sync
```

Manual imports are also available with:

```text
add <path>
```

## Curated corpus workflow

The repository stores corpus metadata, not downloaded papers or generated indexes.

Source of truth:

```text
docs/corpus/corpus_manifest.json
```

Rebuild a local corpus from the manifest:

```bash
uv run python scripts/corpus_sync.py --download-missing --ingest-missing
```

Corpus policy is documented in [docs/CORPUS_POLICY.md](docs/CORPUS_POLICY.md).

## Validation

Run the fixed paper-mode validation harness:

```bash
uv run python scripts/paper_validation_harness.py --top-k 4
```

Run the paper probe set:

```bash
uv run python scripts/paper_probe_runner.py --top-k 4
```

Run the full test suite:

```bash
uv run pytest
```

Validation reports are written locally under:

```text
src/genomics_assistant_data/outputs/reports/
```

These reports are ignored by Git unless deliberately curated.


## Public OA benchmark scaffold

A public open-access paper-mode benchmark scaffold is available in [docs/benchmarks/](docs/benchmarks/). This is separate from the synthetic demo and the local curated-corpus benchmark.

Gold answers for this benchmark must be manually verified from open-access source documents. The template intentionally does not contain Codex-generated ground truth.

## Evidence review GUI

Launch the local Streamlit inspection app:

```bash
uv run streamlit run scripts/review_gui_streamlit.py
```

The app is a developer/debugging interface. It exposes ranked candidates, passage text, chunk metadata, filter decisions, extracted metrics, evidence bundles, structured answers, audit status, timing diagnostics, and validation/probe reports.

## Try the synthetic public demo

This demo does not use real papers, patient data, clinical records, or copyrighted PDFs.

```bash
uv sync
uv run pytest
uv run python scripts/demo_build_sample_corpus.py
uv run python scripts/paper_validation_harness.py --matrix docs/examples/demo_validation_matrix.json --manifest docs/examples/demo_manifest.json --top-k 4
uv run streamlit run scripts/review_gui_streamlit.py

## Quickstart demo

See [docs/QUICKSTART_DEMO.md](docs/QUICKSTART_DEMO.md) for a reproducible local demo path.

## Repository hygiene

Generated corpus files, PDFs, vector indexes, caches, reports, and old local snapshots are intentionally excluded from Git. See:

- [docs/CORPUS_POLICY.md](docs/CORPUS_POLICY.md)
- [docs/PUBLIC_RELEASE_CHECKLIST.md](docs/PUBLIC_RELEASE_CHECKLIST.md)

## Architecture map

```text
src/genoscribe/
  app/          review service and app integration
  corpus/       manifest loading and corpus status helpers
  ingestion/    PDF/text parsing, cleaning, chunk typing, metric extraction
  indexing/     chunking, sparse/dense retrieval, fusion, reranking
  reasoning/    evidence bundles, structured synthesis, verification
  schemas/      typed document/evidence/review/synthesis objects
  storage/      FAISS, SQLite, query cache, provenance storage
  eval/         validation, report parsing, groundedness utilities
  ui/           CLI/TUI surfaces
```

## Design principles

- Evidence first.
- Preserve provenance.
- Prefer `Unknown` or `insufficient_evidence` over risky inference.
- Surface contradictions and missing coverage.
- Keep paper mode as the flagship workflow.
- Keep variant mode explicitly experimental and research-only.

## Current limits

GenoScribe is useful, but it is not magic.

Known limits include:

- metric extraction is still brittle for narrative-only results, figure-only values, and unusual table layouts;
- target-document inference works best when titles, aliases, or explicit context are available;
- the full curated benchmark depends on local corpus sync and is not bundled with the public repo;
- variant mode is experimental and research-only;
- audit states reduce overclaiming, but users still need to inspect cited passages.

The project deliberately prefers `Unknown`, `partially_supported`, or `insufficient_evidence` over confident unsupported claims.

## License and citation

GenoScribe is released under the MIT License. See [LICENSE](LICENSE).

Citation metadata is available in [CITATION.cff](CITATION.cff).

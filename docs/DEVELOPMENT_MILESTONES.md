# Development Milestones

This file summarizes the major development phases that led to the current public release snapshot.

## 1. Evidence-first product boundary

GenoScribe was narrowed from a general assistant concept into a local evidence-review workbench for genomics papers and technical documents.

Key decisions:

- paper mode is the flagship workflow
- assembly mode is secondary and specialized
- variant mode is experimental and research-only
- final answers should be based on structured evidence, not unsupported fluent prose

## 2. Ingestion and document intelligence

The ingestion layer was strengthened for scientific PDFs and technical documents.

Work included:

- PDF parser warning containment for noisy malformed float tokens
- text cleaning for figure-heavy papers
- section and chunk typing (`body`, `caption`, `figure_derived`, `table`, `mixed`, `unknown`)
- document type tagging
- conservative metric extraction with junk-label rejection

## 3. Hybrid retrieval

Retrieval moved beyond sparse-only search while preserving hybrid behavior.

Work included:

- BM25 and sparse fallback retrieval
- MPNet dense embeddings
- FAISS + SQLite persistent vector storage
- manifest-based dense index invalidation
- query embedding caching
- dense/sparse fusion
- reranking and quality filtering

## 4. Scoped evidence handling

Scoped paper queries became a first-class trust problem.

Work included:

- conservative target-document inference from manifest aliases, titles, stems, and explicit context
- target scope overrides for deictic queries such as "this paper"
- target-aware seeding and anchoring where quality thresholds are met
- explicit `off_target_evidence` audit status when scoped evidence drifts away from the requested document

## 5. Evidence bundles

The project added typed evidence objects to avoid treating retrieval results as final answers.

Work included:

- evidence bundle construction
- metric candidates with provenance
- coverage reports
- contradiction tracking
- variant-mode evidence bundle v1, kept experimental and research-only

## 6. Structured synthesis and audit

Paper-mode synthesis was changed so structured findings come before prose.

Work included:

- supported claims
- unsupported requested topics
- limitation notes
- metric summaries
- conflict sets
- answer audit status
- separate rendering step after verification

## 7. Validation harness and probe workflow

Validation became part of normal development rather than an afterthought.

Work included:

- fixed paper-mode validation matrix
- paper probe runner for generalization checks
- report artifacts for validation and probes
- Streamlit report viewer for inspecting failures
- monitoring protocol and monitoring log

Benchmark progression:

```text
4/25 -> 8/25 -> 10/25 -> 14/25 -> 17/25 -> 18/25 -> 19/25 -> 20/25 -> 21/25
```

Current fixed paper-mode benchmark: **21/25 = 84%** on the local curated corpus.

## 8. Public release cleanup

The repository was cleaned so it can be shared without local or copyrighted artifacts.

Work included:

- excluding PDFs, generated library files, vector indexes, caches, and reports
- adding a synthetic demo paper
- adding a demo validation matrix
- adding public release documentation
- making empty-library behavior more graceful

Current public clean-checkout target:

- `uv sync` works
- `uv run python -m pytest` passes with **107 passed / 1 skipped**
- synthetic demo corpus builds
- demo validation passes **5/5**

## 9. Current status

GenoScribe is best described as a developer-facing evidence workbench and research tool with an MVP-grade paper-mode workflow for local use.

It is not a clinical decision system, not a general chatbot, and not yet a product-ready literature platform.

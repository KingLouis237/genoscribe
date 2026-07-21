# Project History

GenoScribe began as a local genomics assistant and became an evidence-first review workbench for genomics papers and technical documents. The project direction was deliberately narrowed around scientific inspection, provenance, validation, and auditability instead of general chatbot behavior.

The public repository starts from a clean release snapshot. The original working repository contained local PDFs, parsed corpus files, vector indexes, caches, report outputs, notebook experiments, and other exploratory artifacts that should not be published. Those artifacts were useful during development, but they are not part of the source release.

## Product direction

The current hierarchy is:

- **Paper mode:** flagship workflow for structured paper review, citation-faithful retrieval, supported and unsupported topic handling, contradiction detection, metric surfacing, and audit-first synthesis.
- **Assembly mode:** secondary, specialized workflow for assembly QC evidence such as QUAST, BUSCO, KAT, Bandage, and related diagnostics.
- **Variant mode:** experimental and research-only workflow for variant-literature evidence assembly. It is not clinical interpretation support.

## Why the repo is clean

The release repository intentionally excludes:

- downloaded PDFs and copyrighted papers
- parsed local library files
- FAISS/vector indexes and SQLite runtime stores
- query caches
- generated validation reports
- notebooks and experimental snapshots
- local `.env` files and secrets

This keeps the repository reproducible and safe to share while preserving the validated source code, demo path, and documentation.

## How development is documented

Because the messy Git history and local corpus artifacts are not published, development history is preserved through explicit documentation:

- `research/ENGINEERING_LOG.md` records design decisions, failed attempts, validation results, and tradeoffs.
- `docs/DEVELOPMENT_MILESTONES.md` summarizes major build phases.
- `docs/VALIDATION_SUMMARY.md` summarizes public-demo and local-corpus validation.
- `docs/KNOWN_LIMITATIONS.md` records current risks and deferred work.

## Current release posture

The public repository is intended to support:

- clean installation with `uv sync`
- full automated tests on a clean checkout
- a synthetic demo corpus that does not require real papers
- a demo validation matrix that exercises the paper-mode pipeline
- local Streamlit inspection of evidence and reports

The full curated-corpus benchmark remains local because it depends on papers and generated artifacts that are not committed to Git.

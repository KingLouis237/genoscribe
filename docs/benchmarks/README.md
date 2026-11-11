# Public Open-Access Paper Benchmark

This directory contains scaffolding for a future public, reproducible paper-mode benchmark.

The goal is to make GenoScribe's flagship paper workflow testable on open-access papers without publishing copyrighted PDFs, local vector indexes, generated reports, or private corpus artifacts.

## Purpose

The public OA benchmark is intended to support:

- reproducible paper-mode evaluation from a clean checkout
- transparent benchmark item definitions
- human-verified gold answers
- explicit audit-state expectations
- separation between evidence retrieval, structured synthesis, and validation outcomes

## Ground-truth policy

Gold answers must be manually written or verified by a human reviewer from the cited open-access source document.

Do not use Codex, ChatGPT, Claude, or any other model to generate benchmark gold answers. A model may help inspect source text, but the final gold answer and support fields must be human verified before a benchmark item is considered valid.

## Separation from other validation paths

This benchmark scaffold is separate from:

- the synthetic demo in `docs/examples/`, which proves clean-checkout functionality only
- the local curated-corpus benchmark, which currently reports 21/25 = 84% but depends on locally synced papers not committed to Git
- paper probe reports, which are generalization diagnostics rather than fixed public gold tests


## Assisted drafting workflow

GenoScribe can assist with drafting candidate OA benchmark items, but drafted items are not gold answers.

Use:

```bash
uv run python scripts/draft_oa_benchmark_items.py --paper-title "Example Open-Access Genomics Paper" --paper-slug example_oa_paper
```

or populate `docs/corpus/oa_benchmark_manifest.json` and run:

```bash
uv run python scripts/draft_oa_benchmark_items.py
```

The script creates five candidate items per paper:

- `scoped_document_query`
- `metric_extraction_query`
- `supported_claim_query`
- `unsupported_topic_query`
- `limitation_conflict_query`

Every drafted item is written with `verification_status = "needs_human_review"`. These items must not be scored, reported as benchmark performance, or treated as gold until a human reviewer fills the verified fields and changes `verification_status` to `human_verified`.

The validator refuses scoring-ready use when any item is not `human_verified`.

## Benchmark tracks

Core benchmark v0 should focus on general paper-mode genomics and bioinformatics papers.

GenomeQC, Solorina, or similar assembly-QC-specific papers must not be placed in the core paper-mode track. If they are used later, they must be assigned to the clearly separate `assembly_qc_specialized` track.

## Current status

`oa_benchmark_v1.template.json` is a template, not a scored benchmark. Items are intentionally empty or marked `TODO` until a human reviewer adds source documents and verifies gold answers.

Future benchmark documents should be open-access and preferably licensed for redistribution, such as CC-BY papers. If redistribution is not allowed, store only metadata and download instructions, not the PDF itself.

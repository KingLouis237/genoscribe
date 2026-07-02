# Corpus Policy

GenoScribe keeps corpus metadata separate from local document files.

## What belongs in Git

- Corpus manifests, such as `docs/corpus/corpus_manifest.json`.
- Validation and probe query definitions.
- Small, human-readable documentation about corpus buckets and expected use.
- Small example reports only when they are intentionally curated and safe to publish.

## What does not belong in Git

- Downloaded PDFs.
- Parsed library JSON files generated from PDFs.
- FAISS indexes, SQLite vector stores, query caches, and runtime cache files.
- Local validation/probe output directories.
- Private papers, embargoed files, clinical data, or documents without redistribution rights.

## Local corpus workflow

Use the manifest to recreate a local working corpus:

```bash
uv run python scripts/corpus_sync.py --download-missing --ingest-missing
```

Generated files stay local under `genomics_assistant_data/` or `src/genomics_assistant_data/` and are ignored by Git.

## Bucket intent

- `core_benchmark`: stable regression set.
- `generalization`: papers used to test transfer beyond the tuning set.
- `stress_test`: difficult files used for ingestion/retrieval stress.
- `mode_specific`: documents tied to paper, assembly, or variant workflows.
- `anti_overfitting`: held-out probes used to detect heuristic overfitting.

## Publication rule

Do not publish a PDF, derived full-text JSON, vector index, or extracted passage store unless redistribution rights are explicit and documented.

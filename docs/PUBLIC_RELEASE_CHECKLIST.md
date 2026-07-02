# Public Release Checklist

Use this checklist before making the repository public.

## Repository hygiene

- [ ] `uv run pytest` passes.
- [ ] `uv run python scripts/paper_validation_harness.py --top-k 4` runs and records the current benchmark score.
- [ ] No generated corpus data is tracked.
- [ ] No PDFs are tracked unless explicitly licensed for redistribution.
- [ ] No vector indexes, SQLite stores, query caches, or local reports are tracked.
- [ ] `_old_genoscribe/` is not tracked.
- [ ] Temporary notebooks, comparison files, and zip artifacts are not tracked.

## Secrets

- [ ] `.env` is ignored and not tracked.
- [ ] `git log -- .env` shows no committed `.env` history.
- [ ] Documentation uses placeholder API keys only.

## Documentation

- [ ] `README.md` describes GenoScribe as an evidence-review workbench.
- [ ] Paper mode is clearly marked as flagship.
- [ ] Assembly mode is clearly marked as secondary.
- [ ] Variant mode is clearly marked as experimental/research-only.
- [ ] Clinical decision support is explicitly disclaimed.
- [ ] `docs/KNOWN_LIMITATIONS.md` is current.
- [ ] `docs/CORPUS_POLICY.md` explains what is and is not included.
- [ ] `docs/QUICKSTART_DEMO.md` gives a reproducible first run.
- [ ] `uv run python scripts/demo_build_sample_corpus.py` builds the synthetic demo corpus from a clean checkout.
- [ ] Demo validation runs with `docs/examples/demo_validation_matrix.json` and `docs/examples/demo_manifest.json`.

## Legal / citation

- [ ] `LICENSE` is present.
- [ ] `CITATION.cff` is present.
- [ ] Corpus redistribution rights are not implied by the code license.

## Release notes

- [ ] Current benchmark score is stated with report path.
- [ ] Known limitations are not hidden.
- [ ] Public examples do not include private, clinical, or restricted data.

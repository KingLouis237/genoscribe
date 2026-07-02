# Corpus Buckets

`docs/corpus/corpus_manifest.json` is the source of truth for corpus composition and bucket tags.

Buckets:
- `core_benchmark`: small stable set used for regression checks.
- `generalization`: diverse papers used to test transfer beyond DYNA-style layouts.
- `stress_test`: ingestion/retrieval edge cases (messy formatting, noisy figures, difficult extraction).
- `mode_specific`: papers explicitly tied to paper/assembly/variant workflows.
- `anti_overfitting`: held-out papers for periodic checks after heuristic changes.

Use `uv run python scripts/corpus_sync.py --download-missing --ingest-missing` to fetch and index missing manifest entries, then inspect the generated `corpus_inventory_*.json` report in `src/genomics_assistant_data/outputs/reports/`.

## Paper-mode validation harness

`docs/corpus/paper_validation_matrix.json` defines a small flagship-paper validation set:
- 2 core benchmark papers
- 2 generalization papers
- 1 stress-test paper

Run:

```bash
uv run python scripts/paper_validation_harness.py
```

This writes `src/genomics_assistant_data/outputs/reports/paper_validation_<timestamp>.json` with:
- query/task outcomes,
- automatic checks,
- manual-review placeholders,
- structured paper outputs (claims, unsupported topics, limitations/conflicts, audit status).

### 2-week paper-mode validation loop

Use this lightweight cadence (no architecture changes required):
1. **Day 1 baseline:** run `paper_validation_harness.py`, review auto-fail rows, and annotate `manual_review` fields in the JSON report.
2. **Days 2-5 focused fixes:** implement only paper-mode trust fixes (scoping, unsupported-topic handling, metric binding), then rerun harness.
3. **Day 6 checkpoint:** compare latest report against baseline (`auto_pass_rate`, off-target audits, unsupported-topic behavior).
4. **Week 2 repeat:** run the same matrix after each paper-mode patch; avoid changing matrix queries mid-sprint unless a query is scientifically invalid.
5. **Sprint close:** archive the final report path and summarize remaining failures in `docs/failure_cases/README.md`.

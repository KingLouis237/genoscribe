# GenoScribe No-Code Validation Monitoring Protocol (1-2 Weeks)

This protocol uses `docs/VALIDATION_CHECKPOINT_2026-04.md` as the baseline and tracks metric-intent risk without backend changes.

## Scope (Do Not Change During This Window)
- No retrieval changes
- No synthesis/audit changes
- No corpus/manifest edits
- No probe-query edits
- No benchmark/probe matrix edits

## Primary Risk Signals to Monitor
1. **Metric-intent with overlap but no surfaced metrics**
   - `final_doc_overlap=True` and `metric_count=0`
2. **Scoped metric query with target overlap but off-target metric claims**
   - `final_doc_overlap=True` and `audit_status=off_target_evidence` on metric query

## Reports to Review Each Cycle
- Latest fixed benchmark report (`paper_validation_*.json`)
- Latest probe report (`paper_probe_report_*.json`)

Review in Streamlit report viewer tab:
- Select report
- Inspect summary + failure breakdown
- Drill into failed rows

## Exact Current Rows to Inspect First

### Benchmark (from current checkpoint)
1. `genome_medicine_clingen_vci_2021 / metric_extraction_query`
   - Why: `metric_minimum_met=False` with target overlap true.

### Probe
1. `rna_seq_best_practices_2016 / metrics_optional`
   - Why: overlap true but `audit_status=off_target_evidence` and high non-target metric contamination risk.
2. `gene_prediction_benchmark_2020 / metrics_optional`
   - Why: overlap true but `metric_count=0` and `audit_status=insufficient_evidence`.
3. `bmc_genomics_benchtop_wgs_2025 / metrics_optional`
   - Why: overlap true but `metric_count=0` despite known metric-bearing document.

## Evidence to Record for Each Inspected Failure
For each tracked row, capture:
1. Report filename
2. Document slug/paper
3. Query type (`metric_query` / `metric_extraction_query`)
4. Query text
5. `target_doc_inferred` (bool)
6. `final_doc_overlap` (bool)
7. `target_scope_source` (if probe)
8. `metric_count`
9. `audit_status`
10. Final document IDs (`final_doc_ids`)
11. Target document IDs (`target_doc_ids`)
12. Top candidates (doc + chunk IDs) from drill-down
13. Rendered output snippet showing whether claimed metrics are target- or non-target-backed
14. Operator diagnosis (one-line)
15. Decision (`fix now` / `known limitation` / `harness pressure` / `defer`)

## Monitoring Cadence (1-2 Weeks)
- **Twice weekly** (e.g., Tue/Fri), run:
  - benchmark harness (unchanged)
  - probe runner (unchanged)
- After each run:
  1. Open latest reports in Streamlit viewer
  2. Fill/update monitoring table rows for tracked failures
  3. Mark trend vs previous run: `improved / unchanged / regressed`

## Monitoring Table Template

Store in a single file and append rows per run.

Recommended file: `docs/VALIDATION_MONITORING_LOG_2026-05.md`

| run_date | report_name | surface | document | query_id_or_type | query_text | target_inferred | final_overlap | target_scope_source | metric_count | audit_status | expected_doc_ids | target_doc_ids | final_doc_ids | diagnosis | decision | trend_vs_prev |
|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|---|
| YYYY-MM-DD | paper_probe_report_...json | probe | bmc_genomics_benchtop_wgs_2025 | metrics_optional | From the benchtop... | true | true | inferred | 0 | insufficient_evidence | [...] | [...] | [...] | Target overlap true but no surfaced metrics in final kept set | known limitation | unchanged |

## Patch-Resume Decision Rules
Resume backend patching only if one of these conditions is met:

1. **Repeated metric-zero pattern**
   - Same metric-intent row shows `final_overlap=True` and `metric_count=0` in **>=3 consecutive runs**.

2. **Cross-document metric-zero generalization**
   - At least **2 different documents** show metric-intent `final_overlap=True` + `metric_count=0` in the same run window.

3. **Repeated off-target metric-claim pattern**
   - Same scoped metric row shows `final_overlap=True` + `audit_status=off_target_evidence` in **>=2 consecutive runs**, with rendered output citing non-target metrics.

4. **Net regression trigger**
   - Overall probe `target_doc_inferred` falls below 95% **or**
   - overall probe `final_doc_overlap` falls below 90% for 2 consecutive runs.

If no trigger fires, keep backend frozen and continue monitoring.

## Out-of-Scope During Monitoring
- No “quick fixes” to aliases/heuristics unless a trigger condition is met.
- No benchmark matrix modifications.
- No UI redesign beyond current report viewer capabilities.

# GenoScribe Validation Checkpoint (2026-04)

This checkpoint captures validated status before further backend changes.

## Scope + Artifacts
- Fixed benchmark report: `src/genomics_assistant_data/outputs/reports/paper_validation_20260424_144109.json`
- Latest probe report: `src/genomics_assistant_data/outputs/reports/paper_probe_report_20260428_175019.json`
- Probe summary CSV: `src/genomics_assistant_data/outputs/reports/paper_probe_summary_20260428_175019.csv`

## 1) Fixed Paper-Mode Benchmark Health
- Score: **21/25 = 84%** (`auto_pass_rate=0.84`)
- Task-type pass split:
  - scoped_document_query: 5/5
  - metric_extraction_query: 4/5
  - supported_claim_query: 4/5
  - unsupported_topic_query: 4/5
  - limitation_conflict_query: 4/5
- Current failure checks (4 failed tasks):
  - `final_doc_overlap`: 2
  - `metric_minimum_met`: 1
  - `target_doc_inferred`: 1
  - `non_insufficient_audit`: 1

## 2) Probe / Generalization Health
- Total probe queries: **22**
- `target_doc_inferred`: **22/22 (100%)**
- `final_doc_overlap`: **21/22 (95.5%)**
- Audit statuses:
  - supported: 7
  - partially_supported: 11
  - off_target_evidence: 2
  - insufficient_evidence: 2
- Probe failures (using current probe fail criteria): **4**
  - by task type: metric_query (3), limitation_conflict_query (1)

## 3) Remaining Failures and Triage

| Surface | Document / Query | Signal | Classification | Rationale |
|---|---|---|---|---|
| Benchmark | `dyna_seed / supported_claim_query` | `final_doc_overlap=False`, `audit=off_target_evidence` | defer | Scoped anchoring miss persists; single-row miss in frozen benchmark period, not enough to reopen broad patching. |
| Benchmark | `dyna_seed / unsupported_topic_query` | `final_doc_overlap=False`, `audit=insufficient_evidence` | harness/query pressure | Unsupported-topic behavior is logically conservative; failure is overlap check pressure rather than unsafe claim behavior. |
| Benchmark | `genome_medicine_clingen_vci_2021 / metric_extraction_query` | `metric_minimum_met=False` with overlap true | known limitation | Narrative/adoption-count metric surfacing remains weak for this paper style. |
| Benchmark | `papadimitriou_seed / limitation_conflict_query` | `target_doc_inferred=False`, overlap true | defer | Inference miss is isolated and partially masked by overlap success; avoid benchmark-tuning drift while patching is paused. |
| Probe | `rna_seq_best_practices_2016 / metrics_optional` | overlap true, `audit=off_target_evidence`, `metric_count=97` | known limitation | Scoped metric claim composition still cites non-target metrics first in mixed retrieval sets. |
| Probe | `gene_prediction_benchmark_2020 / limitations` | `final_doc_overlap=False`, `audit=off_target_evidence` | known limitation | Mixed-mode/figure-heavy target still loses in final composition for this prompt pattern. |
| Probe | `gene_prediction_benchmark_2020 / metrics_optional` | overlap true, `audit=insufficient_evidence`, `metric_count=0` | harness/query pressure | Query asks for explicit model-system metric extraction; current surfaced evidence is sparse/indirect for this path. |
| Probe | `bmc_genomics_benchtop_wgs_2025 / metrics_optional` | overlap true, `audit=insufficient_evidence`, `metric_count=0` | fix now (if backend resumes) | Document contains structured metrics, but selected final rows are non-metric/front-matter; this is a concrete metric-intent surfacing miss. |

## 4) What Is Validated vs Not Validated

### Validated enough for current phase
- Paper-mode scoped retrieval/audit pipeline is stable at 84% on fixed harness.
- Probe scoping robustness improved materially (100% inferred, 95.5% overlap on latest run).
- Report observability is usable (Streamlit report viewer supports summary, breakdowns, drill-down).

### Not yet validated enough
- Metric-intent robustness across narrative + methods papers (repeated probe misses).
- Guaranteed target-first metric citation behavior in mixed evidence sets.
- Generalization reliability outside current 25-doc corpus and current probe phrasing set.

## 5) Recommendation for Next Phase (No Backend Changes in This Checkpoint)
- **Primary recommendation:** keep backend frozen and run a short validation-monitoring loop (1-2 weeks) using current benchmark + probes with the new report viewer.
- Trigger backend patching only if a repeated general failure pattern appears across multiple docs/runs, especially:
  1) metric-intent overlap=true but metric_count=0, or
  2) scoped metric queries with target overlap but off-target metric claims.
- If such repetition is confirmed, run one narrow metric-surfacing sprint; otherwise continue corpus/probe diagnosis.

## 6) Deferred Work
- No retrieval/synthesis/audit changes in this checkpoint.
- No benchmark matrix edits.
- No probe matrix redesign.
- No new framework or UI redesign work beyond current report viewer.

# GenoScribe Failure Cases (2026-03-10)

Each entry captures the query, expectation, observed behavior, evidence (chunk IDs plus exported report paths), and the pipeline stage most likely responsible.

## Case 1 - Stress query returns unrelated passages
- **Query:** `ribosome profiling bias` (assembly / stress benchmark)
- **Expected:** Either no hits or assembly QC passages that explicitly mention ribosome profiling artifacts.
- **Actual:** The final hybrid list contains cardiomyopathy variant summaries from `Marsh_et_al_Pred_variants_2026-03-09_18-50-41.pdf` (chunks 3 and 4) plus a DYNA PLLR caption (chunk 34). None mention ribosome profiling, yet they survived filtering with `mode_boost=1.08`.
- **Evidence:** `genomics_assistant_data/outputs/reports/retrieval_report_20260310_211525.json` → entry `"query": "ribosome profiling bias"` → `hybrid_final` + `filter_decisions` (see chunk IDs 3, 4, 34).
- **Likely stage:** Retrieval / mode filtering. BM25 + dense fusion over-weight generic assembly keywords, and figure quotas are too permissive for figure-derived passages.
- **2026-03-10 analysis:** Informative tokens (`ribosome`, `profiling`) never appeared in those passages, so the old filter only saw the generic words (`assembly`, `bias`) and left them in the final set.
- **Mitigation:** `filter_passages_for_quality` now enforces an informative-term overlap (ignores mode keywords/short tokens) and drops passages when `informative_overlap=0`. See `src/genomics_assistant_data/outputs/reports/retrieval_report_20260310_221737.json` where the same query yields `hybrid_final: []` and every candidate shows `reason: "dropped: no informative-term overlap"`.
- **Status:** Resolved for the current stress benchmark; depends on the informative-term list remaining accurate.

## Case 2 - Foundation-model query still pulls DYNA PLLR figure
- **Query:** `foundation model pathogenicity benchmarks` (paper mode)
- **Expected:** Passages from benchmarking papers only (e.g., `Gene-Pathogenicity-Prediction-using-Genomic-Foundation-Models`, `Frazer_et_al_EVE`).
- **Actual:** The final hybrid set includes `DYNA_2026-03-09_18-53-20.pdf · chunk 44` (a caption describing NT + SpliceBERT PLLR ensembles) even though it is unrelated to foundation models.
- **Evidence:** Same retrieval report as above → entry `"query": "foundation model pathogenicity benchmarks"` → `hybrid_final` shows chunk 44 from DYNA with reason `kept: fused_score=0.514, mode_boost=1.00`.
- **Likely stage:** Mode-aware filtering. Figure chunks are now tagged as `chunk_type="caption"` and the document keeps its `doc_type="variant"`, yet the mode weight (paper) still equals 1.00 so the caption survives.
- **2026-03-10 analysis:** In `src/genomics_assistant_data/outputs/reports/retrieval_report_20260310_230129.json`, the same chunk (44) remains in `hybrid_final` with `chunk_type="caption"` and `doc_type="variant"`, so doc-type boosts/penalties are too small to block it.
- **Mitigation:** Paper-mode now requires figure/caption passages to have structured metrics **and** either strong informative-term overlap or matching doc-type context before retention. Variant captions that lack both are dropped with explicit reasons.
- **Verification:** `src/genomics_assistant_data/outputs/reports/retrieval_report_20260317_192044.json` shows the same query returning only Gene-Pathogenicity passages; DYNA chunk 44 no longer appears in `hybrid_final` and the filter log explains the drop.
- **Status:** Resolved; continue monitoring when new document types are added.

## Case 3 - DYNA metric extraction mislabels models
- **Dataset:** `genomics_assistant_data/outputs/metrics/dyna_metrics_20260310_211525.csv`
- **Expected:** The `Model` column should list DYNA or ESM1b for KL rows, and the `Dataset` column should cite CM/ARM when present.
- **Actual:** Several rows report `Model=AdaBoost` (e.g., “DYNA KL Divergence: 13.2859”, “ESM1b KL Divergence: 12.2986”, “Baseline AUPR: 0.5413”) and leave the dataset as `Unknown`. The heuristic latched onto the AdaBoost baseline text rather than the DYNA/ESM figure labels.
- **Evidence:** Open the CSV (rows with `Chunk=39`) or view the console table produced by the benchmark script.
- **Likely stage:** Extraction heuristics. `_match_from_keywords` prefers AdaBoost because the caption lists the baseline immediately after the metric label; it does not look for CM/ARM tokens near the metric span.
- **2026-03-10 analysis:** The 160-character context window still contained the AdaBoost legend, so the longest keyword kept winning even when the label itself said "DYNA...".
- **Mitigation:** `_match_from_keywords` now checks the metric label before scanning the window, `_dataset_from_context` explicitly looks for CM/ARM/ClinVar tokens, `_looks_like_metric_label` rejects DOI/textbook strings, and the exporter defaults to `Model/Dataset=Unknown` instead of guessing.
- **2026-03-17 review:** `src/genomics_assistant_data/outputs/metrics/dyna_metrics_20260317_184153.csv` now lists DYNA/ESM1b correctly with no AdaBoost mislabels; dataset remains `Unknown` whenever CM/ARM text is absent, which is acceptable but still limits downstream aggregation.
- **Status:** Resolved for DYNA captions. Remaining risk is missing dataset attribution when captions omit CM/ARM text.

## Case 4 - Non-DYNA variant papers still lack structured metrics
- **Document:** `papadimitriou-et-al-2019-predicting-disease-causing-variant-combinations_1__2026-03-09_18-53-49.pdf`
- **Expected:** Structured VarCoPP probabilities (confidence zones, VarCoPP thresholds) labeled with “VarCoPP” or a meaningful shorthand.
- **Actual:** The new junk-rejection heuristics now suppress those rows entirely—`src/genomics_assistant_data/library/papadimitriou-et-al-2019-...json` shows zero extracted metrics after 2026-03-17—so users see no structured values rather than misleading “of SS” entries.
- **Evidence:** Run `uv run python -c "..."` (see sprint notes) to inspect the updated library JSON; `sample_metrics` is empty despite the figure containing VarCoPP confidence-zone thresholds.
- **Likely stage:** Metric extraction heuristics lack table-specific parsers; without model-aware regexes the conservative filters remove everything.
- **2026-03-17 note:** Targeted VarCoPP extractors for Support Score, Classification Score, and confidence-zone thresholds now exist, but previously ingested documents must be rebuilt (e.g., `rebuild_index`) to populate the new metrics.
- **2026-03-17 rebuild:** Re-ingesting `papadimitriou...pdf` and `SHINE...pdf` produced 31 VarCoPP metrics and 8 SHINE metrics; structured CSVs are available at `src/genomics_assistant_data/outputs/metrics/varcopp_metrics_20260317_194016.csv` and `.../shine_metrics_20260317_194016.csv`.
- **Status:** Resolved after rebuild (precision preserved, recall restored). Remaining risk: acronym-only queries (e.g., “CM ARM”) still bypass informative-term gating because tokens shorter than five characters are treated as stopwords.

## Case 5 - Variant bundle needs explicit HGVS identifiers
- **Query:** `LMNA arrhythmia ancestry` (variant mode)
- **Expected:** The variant bundle should tag the LMNA missense finding with a concrete HGVS id (or at least confidently note the lack of one) while still recording ancestry context and class labels.
- **Actual:** The generated bundle lists the passage but keeps `variant_id=Unknown`, `ClinVar classification=Unknown`, and treats the short-token hints (`arm`, `eur`) as telemetry only. Coverage reports flag “variant identifier” and “ClinVar classification” as missing, so downstream tools still cannot reason about the variant.
- **Evidence:** `src/genomics_assistant_data/outputs/reports/variant_bundle_failure_case_20260317_210425.json` (`chunk_id=44` from `Varipred_2026-03-09_18-53-16.pdf`).
- **Likely stage:** Variant evidence assembly relies on HGVS/c.* detection; when authors only mention “LMNA missense” without the explicit identifier, the extractor refuses to guess and the bundle stays anonymous.
- **Mitigation:** Extend `_extract_variant_fields` with synonym tables (e.g., LMNA “E161K”) or leverage nearby tables when doc metadata enumerates the exact HGVS id. Keep today’s conservative behavior (explicit `Unknown`) but surface richer remediation guidance so curators know what to search for.
- **Status:** Open. Variant bundle now documents the gap, yet resolving it still requires parsing external tables or metadata.

## Case 6 - Unicode / spaced HGVS not normalized
- **Query:** `VarCoPP support score confidence zone combination` (variant mode)
- **Document:** `Varcopp_Nassim_2026-03-09_18-53-41-1773078821.pdf` (variant doc id `...8821`)
- **Expected:** Passages that cite variants such as `Nr5a1 c. 991–1g> c` or `c.991-1G>C` in the reference section should be recognized as HGVS strings so VariantCandidates inherit the identifier instead of “Unknown”.
- **Actual (before fix):** The validation run (`variant_bundle_validation_20260318_090756.json`, label “VarCoPP combinations”) reported 47 candidates and nine metrics but zero HGVS ids because the PDF prints “c. 991–1g> c” with an en dash and embedded spaces.
- **Mitigation:** Added Unicode normalization + dash translation + whitespace collapse around `c.`/`p.` tokens (2026-03-18), plus tolerant HGVS regexes. Re-running the validator (`variant_bundle_validation_20260318_182616.json`) now captures `c.991-1G>C` twice, so the variant surfaces with a canonical identifier.
- **Status:** Resolved for the Varcopp reference set; leave the entry visible so future normalization regressions can be measured.

## Case 7 - Corpus overfit risk from DYNA-heavy seed set
- **Query pattern:** Broad paper-mode queries (for example, `pathogenicity benchmark`) on a library dominated by DYNA-adjacent papers.
- **Expected:** Retrieval and metric extraction should generalize across publishers, layouts, and non-cardiac topics.
- **Actual (before corpus pass):** Most benchmark and tuning loops repeatedly hit DYNA/SHINE-style figure captions, so heuristics were validated on a narrow distribution.
- **Evidence:** `src/genomics_assistant_data/library_files/` and `src/genomics_assistant_data/library/` previously contained mostly DYNA-family / variant-predictor documents; no curated bucket metadata existed to separate benchmark vs stress vs holdout.
- **Likely stage:** Evaluation setup and corpus management, not a single retrieval function bug.
- **Mitigation (2026-04-16):** Added curated manifest-driven corpus workflow:
  - `docs/corpus/corpus_manifest.json` (bucket tags + mode tags + source URLs)
  - `scripts/corpus_sync.py` (download + ingest + inventory report)
  - `docs/corpus/README.md` (bucket definitions and sync command)
- **Status:** Mitigated but still open until at least one non-English and one OCR-heavy scanned PDF are added to `stress_test`.

## Case 8 - Paper-mode validation harness baseline shows low auto pass rate
- **Run:** `uv run python scripts/paper_validation_harness.py --top-k 4`
- **Expected:** Core paper-mode validation matrix should pass scoped queries and at least basic metric/support checks across benchmark + generalization papers.
- **Actual (2026-04-17 baseline):** Auto pass rate is `4/25` (`16%`) from `src/genomics_assistant_data/outputs/reports/paper_validation_20260417_122730.json`.
- **Evidence:** Same report summary:
  - `scoped_document_query`: 2/5 passed
  - `metric_extraction_query`: 0/5 passed
  - `supported_claim_query`: 0/5 passed
  - `unsupported_topic_query`: 1/5 passed
  - `limitation_conflict_query`: 1/5 passed
- **Likely stage:** Paper-mode validation surface highlights persistent trust gaps in document scoping, metric surfacing, and support/unsupported labeling consistency.
- **2026-04-19 patch pass:** Applied scoped-target inference hardening, metric-intent surfacing fallback, and stricter audit gating.
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260419_202113.json`
  - Result: `8/25` auto-passed (`32%`) vs prior `4/25` (`16%`)
  - First drops observed in scoped-document failures and some metric-query failures (notably papadimitriou and DYNA metric queries now surface metrics).
- **2026-04-20 scoped-final-selection anchoring pass:** Added bounded scoped target anchoring in retrieval quality filtering (target rescue only within an explicit score margin).
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260420_205941.json`
  - Result: `10/25` auto-passed (`40%`) vs prior `8/25` (`32%`)
  - Failure-check movement: `final_doc_overlap` dropped from `9` to `7`; `target_doc_inferred` stayed at `7`; `metric_minimum_met` stayed at `4`.
- **2026-04-20 scoped target-inference hardening pass:** Added manifest-grounded `scope_aliases` and conservative deictic-query guardrails for deterministic query-to-document anchoring.
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260420_220201.json`
  - Result: `14/25` auto-passed (`56%`) vs prior `10/25` (`40%`)
  - Failure-check movement: `target_doc_inferred` dropped from `7` to `1`; `final_doc_overlap` dropped from `7` to `6`; `metric_minimum_met` remained `4`.
- **2026-04-20 scoped target-seeding pass:** Added paper-mode pre-rerank target seeding when scoped targets are absent from initial pools.
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260420_231504.json`
  - Result: `14/25` auto-passed (`56%`) (no net change from prior run)
  - Failure-check movement: unchanged (`final_doc_overlap=6`, `metric_minimum_met=4`, `target_doc_inferred=1`).
  - Diagnostic note: seeding stage executes for some PLOS scoped queries but returns empty slices under current conservative lexical/noise gates.
- **2026-04-20 scoped target-seeding v2:** Relaxed seeding gate for explicit target docs in paper mode by turning `doc_type != paper` from hard reject into a score penalty (kept overlap/noise/figure gates unchanged).
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260420_234706.json`
  - Result: `17/25` auto-passed (`68%`) vs prior `14/25` (`56%`)
  - Failure-check movement: `final_doc_overlap` improved from `6` to `3`; `metric_minimum_met` remains `4`; `target_doc_inferred` remains `1`.
  - PLOS impact: scoped/document and supported/unsupported scoped tasks now keep target PLOS evidence in final candidates more reliably.
- **2026-04-24 scoped runtime metric signal (paper metric-intent targets only):** Added constrained runtime metric rescue for scoped target figure/caption passages when stored metrics are empty, with strict DOI/year/page metadata rejection and overlap/noise gates.
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260424_113325.json`
  - Result: `18/25` auto-passed (`72%`) vs prior `17/25` (`68%`)
  - Failure-check movement: `metric_minimum_met` reduced from `4` to `3`.
  - Impact: DYNA metric task now passes (`metric_count=4`); PLOS, Gene benchmark, and ClinGen metric tasks remain failing.
- **2026-04-24 table-row metric extraction for benchmark tables:** Added header+row parsing for table blocks (`Model/Method + metric columns + decimal values`) in the metric extractor.
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260424_123240.json`
  - Result: `19/25` auto-passed (`76%`) vs prior `18/25` (`72%`)
  - Failure-check movement: `metric_minimum_met` reduced from `3` to `1`.
  - Impact: Gene Pathogenicity metric query now passes (`metric_count=124` in current top-k retrieval set). Remaining metric-minimum failure is ClinGen VCI.
- **2026-04-24 scoped metric-intent anchoring (target metric figures):** Added a narrow paper-mode metric-intent override so quality-qualified scoped target figure/table passages with structured metrics are not dropped solely by the informative-overlap gate.
  - New run: `src/genomics_assistant_data/outputs/reports/paper_validation_20260424_124451.json`
  - Result: `19/25` auto-passed (`76%`) (no net score gain).
  - PLOS metric task change: `final_doc_overlap` now passes (target chunk retained), but task still fails because `audit_status=off_target_evidence` (`non_off_target_audit=False`).
  - Interpretation: anchoring improved at filtering stage; remaining failure now sits in downstream claim/audit composition where non-target metrics dominate the first supported claims.
- **Residual failures:** still concentrated in target-doc overlap for some PLOS/ClinGen tasks and metric extraction for papers whose passages still contain no extractable structured values.
- **Status:** Open, improved. Keep this as the active flagship-paper trust tracker.


## Case 9 - Scoped metric query cites non-target metrics first despite target metric evidence
- **Query:** `Extract key metrics from this PLOS paper.` (paper mode, scoped)
- **Expected:** When target paper metrics exist in final evidence, supported metric claims should cite target-doc metrics before non-target metrics.
- **Actual (before fix):** Retrieval/filtering preserved target metric chunks (`final_doc_overlap=True`, `metric_minimum_met=True`), but synthesis used non-target metrics from the first metric slots, causing `audit_status=off_target_evidence`.
- **Evidence:**
  - Before: `src/genomics_assistant_data/outputs/reports/paper_validation_20260424_124451.json` (PLOS metric task failed only on `non_off_target_audit=False`).
  - After: `src/genomics_assistant_data/outputs/reports/paper_validation_20260424_133845.json` (PLOS metric task passes with target metric citations in supported claims).
- **Likely stage:** Structured synthesis metric-claim selection order, not retrieval/filtering.
- **Mitigation (2026-04-24):** In `StructuredPaperSynthesizer`, metric-intent scoped queries now prioritize metrics whose `source_doc_id` is in `target_doc_ids`; non-target metrics fill remaining claim slots.
- **Status:** Resolved in current harness run (`20/25`). Keep monitoring for sparse-target cases where target metrics are absent.

## Case 10 - Scoped non-metric trust consistency (partial benchmark relief)
- **Scope:** paper-mode structured synthesis (non-metric, scoped queries).
- **Observed issue:** scoped non-metric queries could still emit off-target supported claims even when no target evidence survived quality gates; separate cases retained target evidence but did not prioritize it in supported-claim ordering.
- **Mitigation (2026-04-24):**
  - suppress off-target supported-claim assembly for scoped unsupported-topic queries when no target coverage remains,
  - prioritize target provenance for scoped non-metric supported claims when target passages are present.
- **Evidence:** `src/genomics_assistant_data/outputs/reports/paper_validation_20260424_144109.json`.
- **Result:** harness improved from `20/25` to `21/25` (`84%`).
- **Targeted outcomes:**
  - `genome_medicine_clingen_vci_2021 / supported_claim_query` now passes (`audit_status=supported`),
  - `dyna_seed / unsupported_topic_query` is now trust-consistent (`insufficient_evidence`, `supported_claims=0`) but still fails auto-check on `final_doc_overlap=False` because retrieval/quality filtering were intentionally unchanged.


## Case 11 - New paper-primary probe shows weak scoped anchoring for assembly-typed benchmark doc
- **Probe source:** `src/genomics_assistant_data/outputs/reports/paper_probe_report_20260425_172612.json`
- **Document:** `gene_prediction_benchmark_2020` (`BMCGenomics_GenePrediction_Benchmark_2020_s12864-020-6707-9-1777130604`)
- **Expected (probe):** Scoped paper-mode queries should surface at least some target-document overlap.
- **Actual:** All 4 probe queries had `target_doc_inferred=False` and `final_doc_overlap=False`; final candidates came from legacy variant papers.
- **Likely stage:** scoped target inference + mode weighting interaction (document ingested as `doc_type=assembly` while probes run in paper mode).
- **Status:** Open by design (no retrieval/alias tuning in corpus-rebalance sprint). Treat as a real transfer gap to evaluate before promoting any new probes into benchmark coverage.

## Case 12 - Deictic scoped queries require explicit caller context
- **Scope:** paper probe runner / evidence review API integration.
- **Observed issue (before fix):** Queries phrased as "this paper" had `target_doc_inferred=False` because query-text inference lacks deterministic document context.
- **Mitigation (2026-04-25):** Added `target_doc_ids_override` to `EvidenceReviewService.run_query` and wired probe runner to pass explicit target doc ids for deictic queries only.
- **Evidence:** New probe reports include `target_scope_source` per row (`context_override`, `inferred`, `none`), making scope provenance auditable.
- **Status:** Mitigated for callers that pass explicit context. Still open for free-text deictic user queries with no active document context (conservative fallback remains).
- **2026-04-27 update:** Added conservative manifest `scope_aliases` for the three new probe docs. Latest probe run (`paper_probe_report_20260427_130241.json`) improved explicit-title target inference from `1/9` to `9/9`, and explicit final overlap from `6/9` to `8/9`. Remaining miss is `gene_prediction_benchmark_2020 / limitation_conflict_query`, now clearly a retrieval/filtering composition issue rather than scope inference.

## Case 13 - New paper-primary probes reveal phrasing-sensitive scope and metric surfacing gaps (probe-only)
- **Artifacts:** `paper_probe_report_20260428_142455.json`, `paper_probe_summary_20260428_142455.csv`.
- **Observed:**
  - `npj_genomicmed_data_sharing_2017 / limitation_conflict_query` failed (`target_doc_inferred=False`, `final_doc_overlap=False`, `target_scope_source=none`).
  - `bmc_genomics_benchtop_wgs_2025 / metric_query` returned `insufficient_evidence` despite `final_doc_overlap=True`.
- **Interpretation:**
  - First failure is a scoped-phrasing mismatch in explicit-title inference.
  - Second failure is likely metric surfacing/extractor pressure, not document scoping.
- **Status:** Probe/generalization findings only; fixed paper benchmark harness remains unchanged.
- **2026-04-28 metadata-only fix:** Added NPJ-specific alias `genomic data sharing collaboration and outsourcing paper`. In `paper_probe_report_20260428_175019.json`, the NPJ limitations probe now resolves (`target_doc_inferred=True`, `final_doc_overlap=True`).

## Case 14 - Scoped metric-target rescue v1 did not clear repeated metric-zero probes
- **Runs:** `paper_probe_report_20260503_172306.json`, `paper_validation_20260503_172356.json`.
- **Intended fix:** scoped target metric-chunk final-composition rescue in retrieval filtering.
- **Observed:**
  - `gene_prediction_benchmark_2020 / metrics_optional` unchanged (`target overlap=true`, `metric_count=0`, `audit=insufficient_evidence`).
  - `bmc_genomics_benchtop_wgs_2025 / metrics_optional` unchanged (`target overlap=true`, `metric_count=0`, `audit=insufficient_evidence`).
- **Diagnosis:** rescue executes too late for these rows because reranked candidate pools do not contain target metric-bearing chunks; there is nothing eligible to promote during final composition.
- **Additional signal:** benchmark run dropped to `20/25` in this pass (`paper_validation_20260503_172356.json`), so patch should be treated as non-improving with possible regression risk.
- **2026-05-03 rollback:** Rescue patch was reverted (code and dedicated tests removed). Baseline behavior restored pending a different upstream candidate-pool strategy.
- **Status:** Reverted failed attempt; keep as a documented dead end.

## Case 15 - Upstream candidate-pool miss for scoped metric-intent target docs
- **Runs before fix:** `paper_probe_report_20260503_174000.json`.
- **Observed:** For `gene_prediction_benchmark_2020 / metrics_optional` and `bmc_genomics_benchtop_wgs_2025 / metrics_optional`, target overlap was true but final target chunks were non-metric (`metric_count=0`), while metric-bearing target chunks existed in the library.
- **Root cause:** metric-bearing target chunks were absent from primary/fallback/dense pools, so rerank/final could not select them.
- **Mitigation (2026-05-03):** Added scoped paper-mode metric-intent target-metric seed injection before rerank (`target_metric_seed` stage):
  - scoped + metric-intent + target-doc only,
  - max 1-2 injected chunks,
  - requires meaningful structured metrics or runtime metric signal,
  - requires overlap/metric-label relevance + noise gate,
  - rejects obvious boilerplate/front-matter/declarations.
- **Outcome:** `paper_probe_report_20260503_235508.json` shows both focus rows improved:
  - `gene_prediction_benchmark_2020 / metrics_optional`: `metric_count 0 -> 11`, `audit insufficient_evidence -> partially_supported`.
  - `bmc_genomics_benchtop_wgs_2025 / metrics_optional`: `metric_count 0 -> 2`, `audit insufficient_evidence -> partially_supported`.
- **Guardrail checks:** Fixed benchmark stayed at `21/25` (`paper_validation_20260503_235541.json`), and PLOS metric task remained passing.
- **Status:** Mitigated with narrow scoped seeding; continue monitoring for boilerplate leakage in new corpora.

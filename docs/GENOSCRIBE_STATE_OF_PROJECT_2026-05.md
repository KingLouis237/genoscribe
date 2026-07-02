# GenoScribe State of Project (2026-05)

## 1) Executive summary

GenoScribe is currently a strong developer-facing evidence workbench for paper-centric genomics review, not a product-ready assistant. The flagship paper workflow is materially validated (fixed harness: 21/25 = 84%), with meaningful gains in scoped retrieval, provenance-aware synthesis, and audit labeling. The project core strength is trust-oriented architecture (evidence objects, audit states, reproducible reports), not fluent generation.

Main gaps are now concentrated in metric-intent robustness across diverse paper styles, plus residual scoped anchoring edge cases. Generalization is improving via probe corpus expansion, but still limited by corpus shape and query phrasing pressure. Strategic direction should remain: stabilize paper mode under broader probes before expanding architecture or polishing product surfaces.

---

## 2) What GenoScribe is now

Validated facts (repo evidence):
- Local evidence-review system framing is explicit in `README.md:35` and `README.md:58`.
- Product hierarchy is explicit:
  - paper mode flagship (`README.md:47`, `AGENTS.md:11`)
  - assembly mode secondary (`AGENTS.md:20`)
  - variant mode experimental (`AGENTS.md:30`)
- Current pipeline prioritizes retrieval -> evidence assembly -> structured synthesis -> audit status, not free-form chat.

Operational reality:
- Best described as a research/developer evidence tool with a usable local review loop (CLI + Streamlit inspection).
- Not clinically deployable and not a generic "ask anything" paper bot.

---

## 3) Current architecture

### Corpus manifest and sync pipeline
- Manifest schema + loading: `src/genoscribe/corpus/catalog.py` (`CorpusDocumentSpec`, `load_manifest`).
- Sync/download/ingest orchestration: `scripts/corpus_sync.py`.
- Corpus metadata includes buckets, modes, aliases, and expected doc typing via `docs/corpus/corpus_manifest.json`.

### Ingestion and chunking
- End-to-end indexing pipeline: `src/genoscribe/indexing/chunker.py` (`build_index_for_file`).
- PDF parsing with scoped pypdf noise suppression: `src/genoscribe/ingestion/parser_pdf.py`.
- Cleaning/sectioning/table-figure processing:
  - `src/genoscribe/ingestion/sectionizer.py`
  - `src/genoscribe/ingestion/table_figure_extractor.py`
  - `src/genoscribe/ingestion/chunk_typing.py` (body/caption/figure/table/mixed/unknown)

### Document metadata and doc_type/chunk_type handling
- Document type inference: `src/genoscribe/ingestion/doc_classifier.py`.
- Chunk typing is persisted into passage metadata and used downstream in retrieval filtering.

### Hybrid retrieval, dense/sparse fusion, reranking/filtering
- Main retrieval engine: `src/genoscribe/retrieval_hybrid.py`.
- Retrieval stages include sparse primary, sparse fallback, dense retrieval, fusion, rerank, and quality filtering.
- Filter decisions include explicit structured reasons (noise penalties, overlap, dedup, figure quota, etc.) in quality filter outputs.

### Dense retrieval persistence/cache
- Embeddings + FAISS index + cache integration:
  - `src/genoscribe/indexing/dense_index.py`
  - `src/genoscribe/indexing/embedder.py`
  - `src/genoscribe/storage/faiss_store.py`
  - `src/genoscribe/storage/query_cache.py`
- Manifest/version invalidation exists for index rebuild safety.

### Scoped target inference and target overrides
- Target doc inference: `infer_target_doc_ids` in `src/genoscribe/retrieval_hybrid.py`.
- Explicit override path (for deictic scoped queries): `EvidenceReviewService.run_query(..., target_doc_ids_override=...)` in `src/genoscribe/app/review_service.py`.

### Evidence bundle construction
- Paper/variant bundle assembly: `src/genoscribe/reasoning/evidence_bundle.py`.
- Bundle includes provenance-bearing metric candidates, coverage notes, contradictions, and coverage gaps.

### Structured synthesis + audit statuses
- Structured synthesis: `src/genoscribe/reasoning/structured_synthesizer.py`.
- Verification + render status categories (`supported`, `partially_supported`, `insufficient_evidence`, `off_target_evidence`, `conflicting_evidence`): `src/genoscribe/schemas/synthesis.py`.
- Renderer transforms structured output to prose only after verification.

### Metric extraction
- Core extractor: `src/genoscribe/ingestion/metric_extractor.py`.
- Includes generalized patterns and conservative filtering to avoid junk labels.
- Remaining weakness: narrative/adoption-count and some table-discovery misses in new probe docs.

### Validation harness, probe runner, monitoring protocol
- Fixed benchmark harness: `scripts/paper_validation_harness.py`.
- Paper probe runner (generalization probes): `scripts/paper_probe_runner.py`.
- Monitoring:
  - checkpoint: `docs/VALIDATION_CHECKPOINT_2026-04.md`
  - protocol: `docs/VALIDATION_MONITORING_PROTOCOL_2026-05.md`
  - log: `docs/VALIDATION_MONITORING_LOG_2026-05.md`

### Streamlit evidence/reports viewer
- GUI entrypoint: `scripts/review_gui_streamlit.py`.
- Report parsing + summaries + drill-down: `src/genoscribe/eval/report_viewer.py`.
- Intended as a local debugging/inspection surface, not product UX.

---

## 4) Current validation status

Fixed benchmark (flagship paper mode):
- Latest fixed report: `src/genomics_assistant_data/outputs/reports/paper_validation_20260503_235541.json`
- Score: 21/25 (84%)
- Known remaining failed rows:
  - `dyna_seed / supported_claim_query`
  - `dyna_seed / unsupported_topic_query`
  - `genome_medicine_clingen_vci_2021 / metric_extraction_query`
  - `papadimitriou_seed / limitation_conflict_query`

Probe/generalization status:
- Latest probe report: `src/genomics_assistant_data/outputs/reports/paper_probe_report_20260503_235508.json`
- Summary:
  - total queries: 22
  - target inferred: 22/22
  - final overlap: 21/22
  - audit mix dominated by `partially_supported` and `supported`; small residual `off_target_evidence`.

Checkpoint governance:
- Benchmark patching intentionally paused; only resumed under monitoring triggers.
- Monitoring protocol is explicit and auditable (`docs/VALIDATION_MONITORING_PROTOCOL_2026-05.md`).

---

## 5) Corpus status

Manifest/library facts (current repo):
- Manifest documents: 25 (`docs/corpus/corpus_manifest.json`)
- Indexed docs in library: 25 (`src/genomics_assistant_data/library_stats.json`)
- Indexed passages: 1069 (`src/genomics_assistant_data/library_stats.json`)

Manifest bucket counts (non-exclusive tags):
- core_benchmark: 4
- generalization: 21
- stress_test: 4
- mode_specific: 15
- anti_overfitting: 12

Manifest mode tags (non-exclusive):
- paper: 25
- variant: 13
- assembly: 5

Indexed primary doc_type shape (library inventory):
- paper: 10
- variant: 10
- assembly: 4
- unknown: 1

Interpretation:
- Paper-mode corpus support is improving but still mixed with substantial variant-oriented content; this can bias retrieval and metric behavior if not controlled by scoped logic.

---

## 6) Strengths

1. Trust-first architecture is real, not cosmetic
   - Structured evidence + audit objects are central, with provenance and explicit insufficiency states.
2. Disciplined incremental engineering
   - Narrow sprints, regression tests, benchmark/probe artifact loops, and explicit rollback behavior.
3. Scoped retrieval governance
   - Target inference, scoped overrides, off-target audit labeling, and overlap diagnostics are materially stronger than standard RAG setups.
4. Reproducibility and inspectability
   - Manifest-driven corpus, fixed benchmark matrix, probe runner, monitoring protocol, Streamlit report inspection.
5. Local-first pragmatism
   - Works as a local evidence workbench with transparent artifact outputs.

---

## 7) Weaknesses / risks

1. Metric-intent fragility across heterogeneous documents
   - Repeated probe issues show upstream discovery/extraction can miss metric-bearing target chunks.
2. Heuristic concentration risk
   - Several gains are heuristic; continuous monitoring is required to avoid regressions on different paper styles.
3. Corpus composition still imperfectly aligned to flagship goals
   - Manifest is paper-tagged, but indexed doc_type composition is still balanced with variant/assembly.
4. Latency/operational scaling remains modest
   - Good for local corpus scale; not yet hardened for large multi-user or high-throughput scenarios.
5. Variant mode maturity is clearly lower
   - Experimental path remains valuable for research but should not drive product identity.

---

## 8) Comparison to similar tools

### Generic RAG over PDFs
- Where GenoScribe is weaker: less plug-and-play chat UX; more setup/discipline required.
- Where GenoScribe is stronger: explicit provenance, audit statuses, scoped target handling, failure visibility.
- Should not compete yet: broad conversational assistant convenience.
- Realistic niche: high-trust local paper evidence review.

### LangChain/LlamaIndex-style literature agents
- Weaker: ecosystem integrations and rapid prototyping breadth.
- Differentiated: tighter retrieval/audit semantics and validation governance without framework sprawl.
- Should not compete yet: framework-scale connectors/agents marketplaces.
- Niche: rigorous, domain-constrained evidence pipeline.

### Elicit / Semantic Scholar assistants
- Weaker: large-scale pre-indexed corpus and polished discovery UX.
- Differentiated: local/private corpus control, explicit scoped review, artifact-level debugging.
- Should not compete yet: broad literature discovery platform role.
- Niche: investigator-controlled evidence auditing for chosen corpora.

### Paper summarization tools
- Weaker: quick one-shot summaries at mass scale.
- Differentiated: synthesis is constrained by evidence + audit states; uncertainty surfaced.
- Should not compete yet: instant-summary convenience tier.
- Niche: trustworthy review where provenance matters more than speed/fluency.

### Enterprise document QA systems
- Weaker: enterprise auth/compliance/workflow features.
- Differentiated: scientific evidence semantics and genomics-specific operating assumptions.
- Should not compete yet: enterprise platform breadth.
- Niche: technical research teams needing transparent evidence mechanics.

### Domain biomedical evidence tools
- Weaker: clinical-grade curation pipelines and regulatory hardening.
- Differentiated: flexible local evidence workbench with explicit audit framing.
- Should not compete yet: clinical decision support.
- Niche: pre-clinical/research literature review and method debugging.

---

## 9) Current maturity level

Most accurate label now: developer evidence workbench + research tool, with an MVP-grade flagship paper workflow for internal use.

Why:
- Enough validation and tooling to be operational and informative.
- Not enough breadth, robustness, or usability hardening for product-ready claims.
- Explicitly not suitable for clinical interpretation.

---

## 10) Productization requirements

To become more product-like (without losing evidence-first identity):

1. Workflow UX hardening
   - A tighter run-review -> inspect-evidence -> export-report path with less manual operator friction.
2. Corpus onboarding quality
   - Clearer upload/import status, corpus integrity checks, and doc-type diagnostics.
3. Metric-intent reliability
   - Better upstream candidate discovery + extraction robustness across document styles.
4. Performance consistency
   - Continued cache/latency tuning and visibility in standard runs.
5. Validation maturity
   - Broader non-overfit probe sets and trend tracking over time.
6. Reporting/export
   - Stable, standardized artifacts suitable for collaborator handoff.
7. Documentation
   - Operational playbooks for operators/collaborators, not just builders.

---

## 11) Recommended roadmap

### Next 2 weeks
- Keep benchmark matrix frozen.
- Run monitoring protocol cadence and probe rounds.
- Focus only on repeated metric-intent failure patterns (already defined trigger rules).
- Improve corpus integrity metadata where mismatches are confirmed.

### Next 1-2 months
- One or two narrow, test-backed sprints on upstream metric candidate discovery/extraction generalization.
- Expand paper-primary probe diversity (text-heavy, methods-heavy, consortium narrative styles).
- Tighten evaluation/report dashboards for faster failure triage.

### Next 3-6 months
- If paper-mode stability holds: formalize paper-mode v1 boundary.
- Add stronger packaging for local team use (install/run/docs hardening).
- Continue assembly mode as secondary with strict scope.
- Keep variant mode research-only until evidence completeness/contradiction quality materially improve.

---

## 12) What not to do next

1. Do not broaden architecture with framework churn (LangChain/LlamaIndex/CrewAI) without a concrete gap.
2. Do not tune heuristics directly to single probe rows.
3. Do not unfreeze benchmark matrix during this monitoring phase.
4. Do not market variant mode as mature or clinical.
5. Do not prioritize UI polish ahead of evidence correctness and audit consistency.

---

## 13) Final positioning statement

GenoScribe is a local, evidence-first genomics paper review workbench with a validated flagship paper workflow and explicit audit semantics. It is currently strongest as a high-trust developer/research tool for provenance-centered literature analysis, not as a general chatbot or clinical decision system. The right strategy now is disciplined paper-mode generalization and metric-intent robustness, while keeping architecture stable and avoiding product drift.

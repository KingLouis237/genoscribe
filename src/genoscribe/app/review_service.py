from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from genoscribe.config import OUTPUT_DIR, TOP_K_DEFAULT
from genoscribe.indexing import DocumentIndex, LibraryStats, load_library, load_library_stats, rebuild_library_stats
from genoscribe.indexing.dense_index import DenseRetriever
from genoscribe.indexing.reranker import DenseReranker
from genoscribe.reasoning.evidence_bundle import MetricCandidate, assemble_paper_evidence, assemble_variant_evidence
from genoscribe.reasoning.query_rewriter import QueryRewriter
from genoscribe.modes.paper_mode import PaperMode
from genoscribe.reasoning.structured_synthesizer import PaperStructuredRenderer
from genoscribe.retrieval_hybrid import FilterDecision, hybrid_collect, infer_target_doc_ids
from genoscribe.schemas.document import Passage
from genoscribe.schemas.review import (
    CandidateView,
    DiagnosticsReport,
    EvidenceBundlePreview,
    FilterTrace,
    MetricRow,
    PassageMetadata,
    ReviewQueryResult,
    StructuredAnswerView,
)
from genoscribe.search import SearchBackendRegistry


class EvidenceReviewService:
    """Facade for running GenoScribe retrieval and exposing structured inspection data."""

    def __init__(self, top_k: int = TOP_K_DEFAULT) -> None:
        self.top_k = top_k
        self.library: List[DocumentIndex] = load_library()
        self.stats: Optional[LibraryStats] = load_library_stats()
        if self.stats is None or self.stats.total_docs != len(self.library):
            self.stats = rebuild_library_stats(self.library)
        self.retriever = DenseRetriever()
        self.retriever.index(self.library)
        self.reranker = DenseReranker(self.retriever)
        self.registry = SearchBackendRegistry()
        self.query_rewriter = QueryRewriter()
        self.paper_mode = PaperMode()
        self.paper_renderer = PaperStructuredRenderer()

    # ------------------------------------------------------------------ public API
    def run_query(
        self,
        *,
        query: str,
        mode: str = "paper",
        top_k: Optional[int] = None,
        target_doc_ids_override: Optional[Sequence[str]] = None,
    ) -> ReviewQueryResult:
        if not self.library:
            raise RuntimeError("Library is empty. Ingest documents before launching the review GUI.")
        effective_k = top_k or self.top_k
        if target_doc_ids_override:
            target_doc_ids = [str(doc_id).strip() for doc_id in target_doc_ids_override if str(doc_id).strip()]
        else:
            target_doc_ids = infer_target_doc_ids(query, self.library)
        rewritten = self.query_rewriter.rewrite(query, mode)
        filtered, timings, stage_hits, decisions = hybrid_collect(
            library=self.library,
            stats=self.stats,
            query=rewritten,
            search_method="bm25",
            search_registry=self.registry,
            dense_retriever=self.retriever,
            reranker=self.reranker,
            mode=mode,
            top_k=effective_k,
            target_doc_ids=target_doc_ids,
            return_decisions=True,
        )
        decision_map = {self._passage_key(dec.passage): dec for dec in decisions}
        passage_map = {self._passage_key(p): p for p in filtered}
        candidates = self._build_candidates(filtered, decision_map)
        metadata = self._build_metadata(filtered)
        filter_traces = self._build_filter_traces(decision_map)
        bundle_preview, metrics, structured_view = self._build_bundle_views(filtered, mode, rewritten, target_doc_ids)
        diagnostics = self._build_diagnostics(timings, stage_hits)
        return ReviewQueryResult(
            mode=mode,
            query=query,
            rewritten_query=rewritten,
            candidates=candidates,
            passage_map=passage_map,
            metadata=metadata,
            filter_traces=filter_traces,
            metrics=metrics,
            bundle_preview=bundle_preview,
            structured_answer=structured_view,
            diagnostics=diagnostics,
            target_doc_ids=target_doc_ids,
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _passage_key(passage: Passage) -> str:
        return f"{passage.doc_id}:{passage.chunk_id}"

    def _build_candidates(self, passages: Sequence[Passage], decisions: Dict[str, FilterDecision]) -> List[CandidateView]:
        rows: List[CandidateView] = []
        for passage in passages:
            key = self._passage_key(passage)
            decision = decisions.get(key)
            summary = (passage.summary or passage.text or "").strip()
            rows.append(
                CandidateView(
                    doc_id=passage.doc_id,
                    source_path=passage.source_path,
                    chunk_id=passage.chunk_id,
                    page=passage.page,
                    chunk_type=passage.chunk_type or ("table" if passage.is_table_or_figure else "body"),
                    doc_type=getattr(passage, "doc_type", "paper") or "paper",
                    summary=summary[:280],
                    fused_score=(decision.fused_score if decision else None),
                    bm25_score=None,
                    rerank_score=None,
                    kept=True,
                    final_rank=decision.final_rank if decision else None,
                )
            )
        return rows

    def _build_metadata(self, passages: Sequence[Passage]) -> Dict[str, PassageMetadata]:
        data: Dict[str, PassageMetadata] = {}
        for passage in passages:
            key = self._passage_key(passage)
            data[key] = PassageMetadata(
                doc_id=passage.doc_id,
                source_path=passage.source_path,
                chunk_id=passage.chunk_id,
                page=passage.page,
                chunk_type=passage.chunk_type or ("table" if passage.is_table_or_figure else "body"),
                doc_type=getattr(passage, "doc_type", "paper") or "paper",
                noise_level=passage.noise_level,
                has_metrics=bool(passage.metrics),
                is_table_or_figure=bool(passage.is_table_or_figure),
            )
        return data

    def _build_filter_traces(self, decisions: Dict[str, FilterDecision]) -> Dict[str, FilterTrace]:
        traces: Dict[str, FilterTrace] = {}
        for key, decision in decisions.items():
            traces[key] = FilterTrace(
                fused_score=decision.fused_score,
                mode_boost=decision.mode_boost,
                noise_penalty=decision.noise_penalty,
                query_overlap=decision.query_overlap,
                informative_overlap=decision.informative_overlap,
                query_weight=decision.query_weight,
                duplicate_of=decision.duplicate_of,
                figure_quota_hit=decision.figure_quota_hit,
                kept=decision.kept,
                reason=decision.reason,
            )
        return traces

    def _build_bundle_views(
        self,
        passages: Sequence[Passage],
        mode: str,
        rewritten_query: str,
        target_doc_ids: Sequence[str],
    ) -> tuple[EvidenceBundlePreview, List[MetricRow], StructuredAnswerView]:
        mode_lower = (mode or "paper").lower()
        if mode_lower == "variant":
            bundle = assemble_variant_evidence(passages, query=rewritten_query)
            metrics = self._metric_rows_from_candidates(bundle)
            preview = EvidenceBundlePreview(
                bundle_type="variant",
                coverage_notes=bundle.coverage.notes,
                coverage_counts={
                    "total_passages": bundle.coverage.total_passages,
                    "variant_candidates": bundle.coverage.variant_candidates,
                    "ancestry_mentions": bundle.coverage.ancestry_mentions,
                    "phenotype_mentions": bundle.coverage.phenotype_mentions,
                },
                contradictions=bundle.contradictions,
                unresolved_requests=bundle.coverage.missing_fields + bundle.coverage.uncovered_requests,
            )
            structured = StructuredAnswerView(
                mode="variant",
                structured=None,
                rendered_text="Variant-mode structured rendering not yet available.",
                audit_status="insufficient_evidence",
                verifier_notes=bundle.coverage.notes,
            )
            return preview, metrics, structured

        # default to paper bundle
        bundle = assemble_paper_evidence(passages, query=rewritten_query, target_doc_ids=target_doc_ids)
        structured_obj = self.paper_mode.generate_structured(
            list(passages), title="Evidence Review", query=rewritten_query, target_doc_ids=list(target_doc_ids)
        )
        rendered_text = self.paper_renderer.render(structured_obj)
        metrics = self._metric_rows(bundle.metrics)
        preview = EvidenceBundlePreview(
            bundle_type="paper",
            coverage_notes=structured_obj.coverage.notes,
            coverage_counts={
                "total_passages": structured_obj.coverage.total_passages,
                "figure_passages": structured_obj.coverage.figure_passages,
                "metric_candidates": structured_obj.coverage.metric_candidates,
            },
            contradictions=[conflict.description for conflict in structured_obj.conflicts],
            unresolved_requests=structured_obj.coverage.missing_terms,
        )
        view = StructuredAnswerView(
            mode="paper",
            structured=structured_obj,
            rendered_text=rendered_text,
            audit_status=structured_obj.audit.render_status if structured_obj.audit else "supported",
            verifier_notes=structured_obj.audit.verifier_notes if structured_obj.audit else [],
        )
        return preview, metrics, view

    def _metric_rows(self, metrics: Sequence[MetricCandidate]) -> List[MetricRow]:
        rows: List[MetricRow] = []
        for metric in metrics:
            rows.append(
                MetricRow(
                    label=metric.label or "Unknown",
                    value=metric.value or "Unknown",
                    model=metric.model or "Unknown",
                    task=metric.task or "Unknown",
                    dataset=metric.dataset or "Unknown",
                    chunk_id=metric.chunk_id,
                    chunk_type=metric.chunk_type,
                    doc_id=metric.source_doc_id,
                    source_path=metric.source_path,
                    page=metric.page,
                    context=metric.context or "",
                    confidence=metric.confidence,
                    confidence_reason=metric.confidence_reason or "",
                )
            )
        return rows

    def _metric_rows_from_candidates(self, bundle) -> List[MetricRow]:
        rows: List[MetricRow] = []
        for candidate in bundle.candidates:
            rows.extend(self._metric_rows(candidate.pathogenicity_metrics))
        return rows

    def _build_diagnostics(self, timings: Dict[str, float], stage_hits: Dict[str, List[Passage]]) -> DiagnosticsReport:
        stage_map = {name: [self._passage_key(p) for p in hits] for name, hits in stage_hits.items()}
        benchmarks = self._collect_benchmark_artifacts()
        cache_stats = self.retriever.cache_stats()
        return DiagnosticsReport(
            timings_ms=timings,
            cache_stats={k: float(v) for k, v in cache_stats.items()},
            stage_hits=stage_map,
            benchmark_artifacts=benchmarks,
        )

    def _collect_benchmark_artifacts(self) -> List[str]:
        artifacts: List[str] = []
        for subdir in ("reports", "latency", "metrics"):
            path = OUTPUT_DIR / subdir
            if not path.exists():
                continue
            for file in sorted(path.glob("*")):
                if file.is_file():
                    artifacts.append(str(file))
        return artifacts


__all__ = ["EvidenceReviewService"]

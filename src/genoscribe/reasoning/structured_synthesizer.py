from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List, Optional, Sequence, Tuple

from genoscribe.reasoning.evidence_bundle import EvidenceBundle
from genoscribe.schemas.synthesis import (
    CitationRef,
    ConflictSet,
    LimitationNote,
    MetricSummary,
    RetrievalCandidate,
    StructuredPaperSynthesis,
    SupportedClaim,
    SynthesisAudit,
    UnsupportedClaim,
)


def _make_citation(metric) -> CitationRef:
    return CitationRef(
        doc_id=metric.source_doc_id,
        source_path=metric.source_path,
        chunk_id=metric.chunk_id,
        page=metric.page,
    )


class StructuredPaperSynthesizer:
    def __init__(self, max_claims: int = 3) -> None:
        self.max_claims = max_claims
        self._positive_keywords = {"higher", "improved", "better", "outperforms", "increase", "boosts", "strong"}
        self._negative_keywords = {"lower", "worse", "decline", "fails", "limited", "bias", "weak", "underperforms"}
        self._token_stopwords = {"model", "models", "dataset", "datasets", "performance", "study", "paper"}
        self._metric_tokens = {
            "metric",
            "metrics",
            "aupr",
            "auc",
            "auroc",
            "precision",
            "recall",
            "accuracy",
            "f1",
            "sensitivity",
            "specificity",
            "pvalue",
            "pvalues",
            "kl",
            "divergence",
        }

    def build(self, bundle: EvidenceBundle, *, title: str, query: Optional[str] = None) -> StructuredPaperSynthesis:
        metric_intent = self._is_metric_query(query)
        unsupported_topic_intent = self._is_unsupported_topic_query(query)
        target_set = set(bundle.coverage.target_doc_ids)
        covered_set = set(bundle.coverage.covered_doc_ids)
        has_target_coverage = bool(target_set & covered_set)
        scoped_non_metric_target_missing = (
            bool(target_set)
            and not metric_intent
            and unsupported_topic_intent
            and bundle.coverage.total_passages > 0
            and not has_target_coverage
        )
        retrieval_candidates: List[RetrievalCandidate] = []
        for passage in bundle.passages[: self.max_claims * 2]:
            summary = (passage.summary or passage.text or "").strip()
            if not summary:
                continue
            retrieval_candidates.append(
                RetrievalCandidate(
                    doc_id=passage.doc_id,
                    source_path=passage.source_path,
                    chunk_id=passage.chunk_id,
                    page=passage.page,
                    chunk_type=passage.chunk_type or ("table" if passage.is_table_or_figure else "body"),
                    summary=summary[:220],
                    kept=True,
                    filter_reason="structured_pipeline",
                )
            )

        claims: List[SupportedClaim] = []
        metrics: List[MetricSummary] = []
        metric_claim_map: dict[str, str] = {}
        selected_metric_candidates = self._select_metric_claim_metrics(
            bundle.metrics,
            metric_intent=metric_intent,
            target_doc_ids=bundle.coverage.target_doc_ids,
        )
        if scoped_non_metric_target_missing:
            selected_metric_candidates = []
        for idx, metric in enumerate(selected_metric_candidates, start=1):
            metric_id = f"metric-{idx}"
            citation = _make_citation(metric)
            metrics.append(
                MetricSummary(
                    id=metric_id,
                    metric_label=metric.label,
                    value=metric.value,
                    model=metric.model,
                    dataset=metric.dataset,
                    task=metric.task,
                    citation=citation,
                )
            )
            claims.append(
                SupportedClaim(
                    id=f"claim-{idx}",
                    statement=f"{metric.model or 'Model'} reported {metric.label}={metric.value} on {metric.dataset or 'dataset'}",
                    support_status="supported",
                    support_strength="direct_metric",
                    support_reason="Metric explicitly reported in cited passage.",
                    evidence_quality="high",
                    citations=[citation],
                    related_metrics=[metric_id],
                )
            )
            metric_claim_map[metric_id] = claims[-1].id

        if not claims and not metric_intent and not scoped_non_metric_target_missing:
            selected_passages = self._select_non_metric_claim_passages(
                bundle.passages,
                target_doc_ids=bundle.coverage.target_doc_ids,
            )
            for idx, passage in enumerate(selected_passages, start=1):
                summary = (passage.summary or passage.text or "").strip()
                if not summary:
                    continue
                citation = CitationRef(
                    doc_id=passage.doc_id,
                    source_path=passage.source_path,
                    chunk_id=passage.chunk_id,
                    page=passage.page,
                )
                claims.append(
                    SupportedClaim(
                        id=f"claim-{idx}",
                        statement=summary[:280],
                        support_status="supported",
                        support_strength="passage_summary",
                        support_reason="Summary derived directly from cited passage.",
                        evidence_quality="medium",
                        citations=[citation],
                        related_metrics=[],
                    )
                )

        unsupported: List[UnsupportedClaim] = []
        for idx, term in enumerate(bundle.coverage.missing_terms, start=1):
            unsupported.append(
                UnsupportedClaim(
                    id=f"unsupported-{idx}",
                    topic=f"Query coverage for '{term}'",
                    requested_terms=[term],
                    reason="No retrieved passage covered this term.",
                    status="insufficient_evidence",
                    suggested_action=f"Search additional documents for '{term}'.",
                )
            )
        if metric_intent and not metrics:
            unsupported.append(
                UnsupportedClaim(
                    id=f"unsupported-metric-{len(unsupported) + 1}",
                    topic="Requested quantitative metrics",
                    requested_terms=["metrics"],
                    reason="Query requested explicit metrics, but no structured metric evidence was surfaced.",
                    status="insufficient_evidence",
                    suggested_action="Inspect target figures/tables manually or expand retrieval scope.",
                )
            )

        limitations: List[LimitationNote] = []
        for idx, note in enumerate(bundle.coverage.notes, start=1):
            limitations.append(
                LimitationNote(
                    id=f"limitation-{idx}",
                    kind="coverage",
                    description=note,
                    citations=[],
                )
            )

        conflicts: List[ConflictSet] = []
        metric_conflicts = self._detect_metric_conflicts(metrics, metric_claim_map)
        conflicts.extend(metric_conflicts)
        narrative_conflicts = self._detect_narrative_conflicts(claims, start_idx=len(conflicts))
        conflicts.extend(narrative_conflicts)

        audit = SynthesisAudit(
            render_status="supported" if claims else "insufficient_evidence",
            verifier_notes=[],
            dropped_claim_ids=[],
        )
        if target_set and bundle.coverage.total_passages > 0:
            if not has_target_coverage:
                if scoped_non_metric_target_missing:
                    audit.render_status = "insufficient_evidence"
                    limitations.append(
                        LimitationNote(
                            id=f"limitation-target-{len(limitations) + 1}",
                            kind="coverage",
                            description=(
                                "No quality-qualified target-document evidence remained after filtering; "
                                "withholding off-target supported claims."
                            ),
                            citations=[],
                        )
                    )
                else:
                    audit.render_status = "off_target_evidence"
                    limitations.append(
                        LimitationNote(
                            id=f"limitation-target-{len(limitations) + 1}",
                            kind="coverage",
                            description="Target documents not represented: " + ", ".join(bundle.coverage.target_doc_ids),
                            citations=[],
                        )
                    )
        if target_set and claims:
            claim_doc_ids = {
                citation.doc_id for claim in claims for citation in claim.citations if citation.doc_id
            }
            if claim_doc_ids and not (claim_doc_ids & target_set):
                audit.render_status = "off_target_evidence"
                limitations.append(
                    LimitationNote(
                        id=f"limitation-target-{len(limitations) + 1}",
                        kind="coverage",
                        description="Supported claims cite only non-target documents.",
                        citations=[],
                    )
                )
        if metric_intent and not metrics:
            audit.render_status = "insufficient_evidence"
            limitations.append(
                LimitationNote(
                    id=f"limitation-metric-{len(limitations) + 1}",
                    kind="coverage",
                    description="Metric-focused request could not be satisfied with structured metrics.",
                    citations=[],
                )
            )
        if audit.render_status == "supported" and unsupported:
            if len(unsupported) >= len(claims):
                audit.render_status = "partially_supported"
        if conflicts and audit.render_status == "supported":
            audit.render_status = "conflicting_evidence"

        return StructuredPaperSynthesis(
            title=title,
            query=query,
            retrieval_candidates=retrieval_candidates,
            supported_claims=claims,
            unsupported_claims=unsupported,
            limitations=limitations,
            metric_summaries=metrics,
            coverage=bundle.coverage,
            conflicts=conflicts,
            audit=audit,
        )

    def _select_metric_claim_metrics(
        self,
        metric_candidates,
        *,
        metric_intent: bool,
        target_doc_ids: Sequence[str],
    ):
        if not metric_candidates:
            return []
        if not metric_intent or not target_doc_ids:
            return list(metric_candidates[: self.max_claims])
        target_set = set(target_doc_ids)
        target_metrics = [metric for metric in metric_candidates if metric.source_doc_id in target_set]
        if not target_metrics:
            return list(metric_candidates[: self.max_claims])
        non_target_metrics = [metric for metric in metric_candidates if metric.source_doc_id not in target_set]
        ordered = target_metrics + non_target_metrics
        return ordered[: self.max_claims]

    def _select_non_metric_claim_passages(
        self,
        passages: Sequence,
        *,
        target_doc_ids: Sequence[str],
    ):
        if not passages:
            return []
        if not target_doc_ids:
            return list(passages[: self.max_claims])
        target_set = set(target_doc_ids)
        target_passages = [passage for passage in passages if passage.doc_id in target_set]
        if not target_passages:
            return list(passages[: self.max_claims])
        non_target_passages = [passage for passage in passages if passage.doc_id not in target_set]
        ordered = target_passages + non_target_passages
        return ordered[: self.max_claims]

    def _is_metric_query(self, query: Optional[str]) -> bool:
        if not query:
            return False
        tokens = {
            re.sub(r"[^a-z0-9]+", "", token.lower())
            for token in re.findall(r"[A-Za-z0-9._+-]+", query)
        }
        return bool(tokens & self._metric_tokens)

    def _is_unsupported_topic_query(self, query: Optional[str]) -> bool:
        if not query:
            return False
        normalized = " ".join(query.lower().split())
        return "what are" in normalized and "paper" in normalized

    def _detect_metric_conflicts(
        self,
        metrics: Sequence[MetricSummary],
        metric_claim_map: Dict[str, str],
    ) -> List[ConflictSet]:
        conflicts: List[ConflictSet] = []
        grouped: Dict[Tuple[str, str], List[MetricSummary]] = {}
        for metric in metrics:
            key = (metric.metric_label.lower(), (metric.dataset or "").lower())
            grouped.setdefault(key, []).append(metric)
        conflict_idx = 0
        for _, metric_list in grouped.items():
            values = {metric.value for metric in metric_list}
            if len(values) <= 1:
                continue
            conflict_idx += 1
            description = (
                f"Conflicting {metric_list[0].metric_label} values on {metric_list[0].dataset or 'dataset'}: "
                + ", ".join(f"{m.value} ({m.model})" for m in metric_list)
            )
            citation_refs = [metric.citation for metric in metric_list]
            related_claim_ids = [
                metric_claim_map.get(metric.id)
                for metric in metric_list
                if metric_claim_map.get(metric.id)
            ]
            conflicts.append(
                ConflictSet(
                    id=f"conflict-metric-{conflict_idx}",
                    conflict_type="metric_value_conflict",
                    description=description,
                    status="conflicting_evidence",
                    citation_refs=citation_refs,
                    related_claim_ids=related_claim_ids,
                )
            )
        return conflicts

    def _detect_narrative_conflicts(
        self,
        claims: Sequence[SupportedClaim],
        start_idx: int = 0,
    ) -> List[ConflictSet]:
        conflicts: List[ConflictSet] = []
        conflict_count = start_idx
        tokens_cache: Dict[str, set] = {}
        sentiment_cache: Dict[str, int] = {}

        def tokens(statement: str) -> set:
            key = statement
            if key in tokens_cache:
                return tokens_cache[key]
            cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in statement)
            toks = {tok for tok in cleaned.split() if len(tok) >= 5 and tok not in self._token_stopwords}
            tokens_cache[key] = toks
            return toks

        def sentiment(statement: str) -> int:
            if statement in sentiment_cache:
                return sentiment_cache[statement]
            lowered = statement.lower()
            score = 0
            if any(word in lowered for word in self._positive_keywords):
                score += 1
            if any(word in lowered for word in self._negative_keywords):
                score -= 1
            sentiment_cache[statement] = score
            return score

        for i, claim_a in enumerate(claims):
            sent_a = sentiment(claim_a.statement)
            if sent_a == 0:
                continue
            tokens_a = tokens(claim_a.statement)
            if not tokens_a:
                continue
            for j in range(i + 1, len(claims)):
                claim_b = claims[j]
                sent_b = sentiment(claim_b.statement)
                if sent_b == 0 or sent_a * sent_b >= 0:
                    continue
                shared = tokens_a & tokens(claim_b.statement)
                if not shared:
                    continue
                conflict_count += 1
                description = (
                    f"Narrative disagreement on {'/'.join(sorted(shared))[:40]}: "
                    f"'{claim_a.statement[:90]}' vs '{claim_b.statement[:90]}'"
                )
                citations = []
                if claim_a.citations:
                    citations.append(claim_a.citations[0])
                if claim_b.citations:
                    citations.append(claim_b.citations[0])
                conflicts.append(
                    ConflictSet(
                        id=f"conflict-narrative-{conflict_count}",
                        conflict_type="narrative_conflict",
                        description=description,
                        status="conflicting_evidence",
                        citation_refs=citations,
                        related_claim_ids=[claim_a.id, claim_b.id],
                    )
                )
        return conflicts


class StructuredVerifier:
    def verify(self, synthesis: StructuredPaperSynthesis) -> StructuredPaperSynthesis:
        kept_claims: List[SupportedClaim] = []
        dropped: List[str] = []
        for claim in synthesis.supported_claims:
            if claim.citations:
                kept_claims.append(claim)
                continue
            dropped.append(claim.id)
            synthesis.unsupported_claims.append(
                UnsupportedClaim(
                    id=f"{claim.id}-unsupported",
                    topic=claim.statement[:80],
                    requested_terms=[],
                    reason="Claim dropped because no supporting citation was attached.",
                    status="insufficient_evidence",
                    suggested_action="Re-run retrieval or cite passage explicitly.",
                )
            )
        synthesis.supported_claims = kept_claims
        if dropped:
            synthesis.audit.verifier_notes.append(
                f"Dropped {len(dropped)} claim(s) lacking citations: {', '.join(dropped)}."
            )
            synthesis.audit.dropped_claim_ids.extend(dropped)
            if not kept_claims:
                synthesis.audit.render_status = "insufficient_evidence"
        if synthesis.audit.render_status == "supported" and synthesis.unsupported_claims:
            if len(synthesis.unsupported_claims) >= max(1, len(kept_claims)):
                synthesis.audit.render_status = "partially_supported"
                synthesis.audit.verifier_notes.append(
                    "Downgraded to partially_supported because unsupported topics are not lower than supported claims."
                )
        return synthesis


class PaperStructuredRenderer:
    def render(self, synthesis: StructuredPaperSynthesis) -> str:
        lines: List[str] = [f"# {synthesis.title}"]
        if synthesis.query:
            lines.append(f"Query: {synthesis.query}")
        if synthesis.retrieval_candidates:
            lines.append("\n## Retrieval candidates")
            for cand in synthesis.retrieval_candidates:
                doc_name = Path(cand.source_path).name
                lines.append(
                    f"- chunk {cand.chunk_id} ({cand.chunk_type}) in {doc_name}: {cand.summary}"
                )
        lines.append("\n## Supported claims")
        if not synthesis.supported_claims:
            lines.append("No supported claims; see unsupported topics below.")
        for idx, claim in enumerate(synthesis.supported_claims, start=1):
            lines.append(f"{idx}. {claim.statement} ({claim.support_reason})")
            for citation in claim.citations:
                doc_name = Path(citation.source_path).name
                lines.append(f"   - citation: {doc_name} · chunk {citation.chunk_id} (page {citation.page or 'n/a'})")
        if synthesis.metric_summaries:
            lines.append("\n## Metrics")
            for metric in synthesis.metric_summaries:
                doc_name = Path(metric.citation.source_path).name
                lines.append(
                    f"- {metric.metric_label}={metric.value} ({metric.model}, {metric.dataset}, chunk {metric.citation.chunk_id} in {doc_name})"
                )
        if synthesis.unsupported_claims:
            lines.append("\n## Unsupported topics")
            for item in synthesis.unsupported_claims:
                lines.append(f"- {item.topic}: {item.reason} (suggestion: {item.suggested_action})")
        if synthesis.limitations:
            lines.append("\n## Limitations")
            for note in synthesis.limitations:
                lines.append(f"- {note.description}")
        if synthesis.conflicts:
            lines.append("\n## Conflicts")
            for conflict in synthesis.conflicts:
                lines.append(f"- {conflict.description}")
                for citation in conflict.citation_refs:
                    doc_name = Path(citation.source_path).name
                    lines.append(f"   * {doc_name} chunk {citation.chunk_id}")
        lines.append(
            f"\nCoverage: {synthesis.coverage.total_passages} passages | "
            f"{synthesis.coverage.metric_candidates} metrics | "
            f"render status: {synthesis.audit.render_status}"
        )
        return "\n".join(lines)


__all__ = ["StructuredPaperSynthesizer", "StructuredVerifier", "PaperStructuredRenderer"]

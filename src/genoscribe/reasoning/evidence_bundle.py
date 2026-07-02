from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from genoscribe.ingestion.abbrev_utils import LONG_FORM_HINTS
from genoscribe.ingestion.metric_extractor import extract_metrics
from genoscribe.schemas.document import Passage


@dataclass
class MetricCandidate:
    label: str
    value: str
    model: str
    dataset: str
    task: str
    chunk_id: int
    chunk_type: str
    doc_type: str
    page: Optional[int]
    source_doc_id: str
    source_path: str
    context: str
    confidence: float = 0.6
    confidence_reason: str = ""


@dataclass
class CoverageReport:
    total_passages: int
    figure_passages: int
    metric_candidates: int
    missing_terms: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    target_doc_ids: List[str] = field(default_factory=list)
    covered_doc_ids: List[str] = field(default_factory=list)


@dataclass
class EvidenceBundle:
    passages: List[Passage]
    metrics: List[MetricCandidate]
    coverage: CoverageReport
    target_doc_ids: List[str] = field(default_factory=list)
    covered_doc_ids: List[str] = field(default_factory=list)


def _metric_candidates_from_passage(passage: Passage) -> List[MetricCandidate]:
    metrics: List[MetricCandidate] = []
    for metric in getattr(passage, "metrics", []) or []:
        chunk_type = passage.chunk_type or ("table" if passage.is_table_or_figure else "body")
        doc_type = getattr(passage, "doc_type", "paper") or "paper"
        context = metric.get("context", "")
        metrics.append(
            MetricCandidate(
                label=metric.get("label", "Unknown"),
                value=metric.get("value", ""),
                model=metric.get("model", "Unknown"),
                dataset=metric.get("dataset", "Unknown"),
                task=metric.get("task", "Unknown"),
                chunk_id=metric.get("chunk_id", passage.chunk_id),
                chunk_type=chunk_type,
                doc_type=doc_type,
                page=metric.get("page", passage.page),
                source_doc_id=metric.get("source_doc_id", passage.doc_id),
                source_path=metric.get("source_path", passage.source_path),
                context=context,
                confidence=0.7 if chunk_type == "body" else 0.6,
                confidence_reason="body metric" if chunk_type == "body" else "figure/table metric",
            )
        )
    return metrics


def _normalize_hgvs_region(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.translate(DASH_TRANSLATION)
    normalized = normalized.replace("\u00A0", " ")
    normalized = re.sub(r"(c\.|p\.)\s+", r"\1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r">\s+", ">", normalized)
    normalized = re.sub(r"\s+>", ">", normalized)
    return normalized


def _canonicalize_hgvs(value: Optional[str]) -> str:
    if not value:
        return "Unknown"
    cleaned = value.replace("(", "").replace(")", "").replace(" ", "")
    if not cleaned:
        return "Unknown"
    prefix = cleaned[:2].lower()
    remainder = cleaned[2:]
    return prefix + remainder.upper()


DASH_TRANSLATION = {
    ord("–"): ord("-"),
    ord("—"): ord("-"),
    ord("−"): ord("-"),
    ord("‒"): ord("-"),
    ord("‑"): ord("-"),
    ord("﹘"): ord("-"),
}


VARIANT_ID_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"(c\.[0-9]+[+-]?[0-9]*[ACGT]>[ACGT])", re.IGNORECASE),
    re.compile(r"(p\.[A-Za-z]{3}[0-9]+[A-Za-z]{3})"),
    re.compile(r"(rs[0-9]+)", re.IGNORECASE),
)
HGVS_PROTEIN_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"(p\.\(?[A-Za-z]{3}[0-9]+[A-Za-z]{3}\)?)", re.IGNORECASE),
    re.compile(r"(p\.[A-Za-z][0-9]+[A-Za-z])", re.IGNORECASE),
)
GENE_BEFORE_HGVS = re.compile(r"\b([A-Z0-9]{2,10})\b(?=\s+c\.)")
GENE_NEAR_VARIANT = re.compile(r"\b([A-Z0-9]{2,10})\b(?=\s+(?:variant|mutation))")
GENE_AFTER_KEYWORD = re.compile(r"gene\s+([A-Z0-9-]{2,10})", re.IGNORECASE)
PHENOTYPE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "cardiomyopathy": ("cardiomyopathy", "dilated cardiomyopathy", "hypertrophic cardiomyopathy"),
    "arrhythmia": ("arrhythmia", "long qt", "atrial fibrillation"),
    "epilepsy": ("epilepsy", "seizure"),
    "cancer": ("cancer", "oncogenic", "tumor"),
}
ANCESTRY_KEYWORDS: Dict[str, str] = {
    "african ancestry": "African ancestry",
    "african cohort": "African ancestry",
    "african": "African ancestry",
    "african descent": "African ancestry",
    "european ancestry": "European ancestry",
    "european cohort": "European ancestry",
    "european": "European ancestry",
    "european descent": "European ancestry",
    "asian ancestry": "Asian ancestry",
    "asian cohort": "Asian ancestry",
    "asian": "Asian ancestry",
    "south asian": "South Asian ancestry",
    "east asian": "East Asian ancestry",
    "middle eastern": "Middle Eastern ancestry",
    "latino ancestry": "Latino ancestry",
    "latino": "Latino ancestry",
    "ashkenazi": "Ashkenazi ancestry",
    "afro": "African ancestry",
    "ancestry": "Ancestry described",
}
COHORT_KEYWORDS: Dict[str, str] = {
    "cardiomyopathy": "cardiomyopathy cohort",
    "arrhythmia": "arrhythmia cohort",
    "cm": "cardiomyopathy cohort",
    "arm": "arrhythmia cohort",
}
CASE_PATTERN = re.compile(r"(?:n\s*=\s*)?(\d+)\s*(?:cases?|patients|probands)", re.IGNORECASE)
CONTROL_PATTERN = re.compile(r"(?:n\s*=\s*)?(\d+)\s*(?:controls?|healthy controls?)", re.IGNORECASE)
GNOMAD_PATTERN = re.compile(r"gnomad[^0-9]*(\d+(?:\.\d+)?(?:e-?\d+)?%?)", re.IGNORECASE)
CLINVAR_TERMS: Tuple[Tuple[str, str], ...] = (
    ("likely pathogenic", "Likely pathogenic"),
    ("pathogenic", "Pathogenic"),
    ("likely benign", "Likely benign"),
    ("benign", "Benign"),
    ("uncertain significance", "Variant of uncertain significance"),
    ("vus", "Variant of uncertain significance"),
)
SHORT_TOKEN_SUPPORT = set(LONG_FORM_HINTS.keys())


@dataclass
class VariantCandidate:
    variant_id: str
    hgvs: str
    gene: str
    phenotype: str
    disease: str
    cohort: str
    ancestry: str
    case_count: Optional[int]
    control_count: Optional[int]
    clinvar_significance: str
    gnomad_frequency: str
    pathogenicity_metrics: List[MetricCandidate]
    chunk_id: int
    chunk_type: str
    doc_type: str
    page: Optional[int]
    source_doc_id: str
    source_path: str
    text_excerpt: str
    short_token_hits: List[str]
    confidence: float = 0.4
    confidence_reason: str = ""


@dataclass
class VariantCoverageReport:
    total_passages: int
    variant_candidates: int
    ancestry_mentions: int
    phenotype_mentions: int
    missing_fields: List[str] = field(default_factory=list)
    uncovered_requests: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class VariantEvidenceBundle:
    passages: List[Passage]
    candidates: List[VariantCandidate]
    coverage: VariantCoverageReport
    contradictions: List[str] = field(default_factory=list)


def _query_terms(query: Optional[str]) -> List[str]:
    if not query:
        return []
    tokens = {match.lower() for match in re.findall(r"[A-Za-z0-9]+", query) if len(match) >= 5}
    return sorted(tokens)


FRAMING_TERMS = {"paper", "document", "article", "manuscript"}
METRIC_QUERY_HINTS = {
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


def _metric_intent(query: Optional[str]) -> bool:
    if not query:
        return False
    normalized_tokens = {
        re.sub(r"[^a-z0-9]+", "", token.lower())
        for token in re.findall(r"[A-Za-z0-9._+-]+", query)
    }
    return bool(normalized_tokens & METRIC_QUERY_HINTS)


def _runtime_metric_candidates_from_passage(passage: Passage) -> List[MetricCandidate]:
    source_text = passage.raw_text or passage.text or ""
    if not source_text.strip():
        return []
    extracted = extract_metrics(source_text, page=passage.page)
    if not extracted:
        return []
    candidates: List[MetricCandidate] = []
    chunk_type = passage.chunk_type or ("table" if passage.is_table_or_figure else "body")
    doc_type = getattr(passage, "doc_type", "paper") or "paper"
    for metric in extracted:
        candidates.append(
            MetricCandidate(
                label=metric.get("label", "Unknown"),
                value=metric.get("value", ""),
                model=metric.get("model", "Unknown"),
                dataset=metric.get("dataset", "Unknown"),
                task=metric.get("task", "Unknown"),
                chunk_id=passage.chunk_id,
                chunk_type=chunk_type,
                doc_type=doc_type,
                page=passage.page,
                source_doc_id=passage.doc_id,
                source_path=passage.source_path,
                context=metric.get("context", ""),
                confidence=0.45,
                confidence_reason="runtime metric extraction fallback",
            )
        )
    return candidates


def assemble_paper_evidence(
    passages: Sequence[Passage],
    query: Optional[str] = None,
    target_doc_ids: Optional[Sequence[str]] = None,
) -> EvidenceBundle:
    metric_candidates: List[MetricCandidate] = []
    figure_passages = 0
    notes: List[str] = []
    query_terms = _query_terms(query)
    metric_intent = _metric_intent(query)
    covered_terms: set[str] = set()
    target_ids = list(target_doc_ids or [])
    covered_doc_ids = sorted({p.doc_id for p in passages})

    for passage in passages:
        if passage.chunk_type in {"caption", "figure_derived", "table"}:
            figure_passages += 1
        searchable = f"{passage.summary or ''} {(passage.text or '')}".lower()
        for term in query_terms:
            if term in searchable:
                covered_terms.add(term)
        passage_metrics = _metric_candidates_from_passage(passage)
        if metric_intent and not passage_metrics:
            passage_metrics = _runtime_metric_candidates_from_passage(passage)
        metric_candidates.extend(passage_metrics)
    if not metric_candidates:
        notes.append("No structured metrics surfaced; consider manual review.")
        if metric_intent:
            notes.append("Metric-focused query returned no structured metrics after runtime fallback extraction.")
    missing_terms = sorted(term for term in (set(query_terms) - covered_terms) if term not in FRAMING_TERMS)
    if missing_terms:
        notes.append("Missing coverage for query terms: " + ", ".join(missing_terms))
    if target_ids and not (set(target_ids) & set(covered_doc_ids)):
        notes.append("Target documents not represented: " + ", ".join(target_ids))
    coverage = CoverageReport(
        total_passages=len(passages),
        figure_passages=figure_passages,
        metric_candidates=len(metric_candidates),
        missing_terms=missing_terms,
        notes=notes,
        target_doc_ids=target_ids,
        covered_doc_ids=covered_doc_ids,
    )
    return EvidenceBundle(
        passages=list(passages),
        metrics=metric_candidates,
        coverage=coverage,
        target_doc_ids=target_ids,
        covered_doc_ids=covered_doc_ids,
    )


def _first_match(patterns: Sequence[re.Pattern[str]], text: str) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            if groups:
                return groups[0]
            return match.group(0)
    return ""


def _normalize_value(value: Optional[str]) -> str:
    value = (value or "").strip()
    return value if value else "Unknown"


def _detect_gene(text: str) -> str:
    match = GENE_BEFORE_HGVS.search(text)
    if match:
        return match.group(1)
    match = GENE_NEAR_VARIANT.search(text)
    if match:
        return match.group(1)
    match = GENE_AFTER_KEYWORD.search(text)
    if match:
        return match.group(1).upper()
    return "Unknown"


def _detect_phenotype(text_lower: str, hint: Optional[str]) -> Tuple[str, str]:
    if hint:
        cleaned = hint.strip()
        return cleaned, cleaned
    for label, keywords in PHENOTYPE_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return label, label
    return "Unknown", "Unknown"


def _detect_cohort(text_lower: str, short_tokens: Sequence[str]) -> str:
    for keyword, label in COHORT_KEYWORDS.items():
        if keyword in text_lower:
            return label
    for token in short_tokens:
        if token in {"cm", "arm"}:
            return COHORT_KEYWORDS[token]
    return "Unknown"


def _detect_ancestry(text_lower: str, short_tokens: Sequence[str]) -> str:
    for keyword in sorted(ANCESTRY_KEYWORDS, key=len, reverse=True):
        if keyword in text_lower:
            return ANCESTRY_KEYWORDS[keyword]
    for token in short_tokens:
        if token in {"afr", "eur", "lat", "eas", "sas"}:
            long_form = LONG_FORM_HINTS.get(token, "")
            if long_form:
                return long_form.title()
            if token == "afr":
                return "African ancestry"
            if token == "eur":
                return "European ancestry"
    if "ancestry" in text_lower:
        return "Ancestry described"
    return "Unknown"


def _extract_case_control(text_lower: str) -> Tuple[Optional[int], Optional[int]]:
    case_match = CASE_PATTERN.search(text_lower)
    control_match = CONTROL_PATTERN.search(text_lower)
    case_count = int(case_match.group(1)) if case_match else None
    control_count = int(control_match.group(1)) if control_match else None
    return case_count, control_count


def _extract_clinvar_significance(text_lower: str) -> str:
    if "clinvar" not in text_lower and "classification" not in text_lower:
        return "Unknown"
    for token, label in CLINVAR_TERMS:
        if token in text_lower:
            return label
    return "Unknown"


def _extract_gnomad_frequency(text_lower: str) -> str:
    match = GNOMAD_PATTERN.search(text_lower)
    if match:
        return match.group(1)
    return "Unknown"


def _short_token_hits(short_tokens: Sequence[str]) -> List[str]:
    hits: List[str] = []
    for token in short_tokens or []:
        if token in SHORT_TOKEN_SUPPORT:
            long_form = LONG_FORM_HINTS.get(token, "")
            hits.append(f"{token} ({long_form})" if long_form else token)
    return hits


def _context_hash(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    digest = hashlib.sha1(normalized.lower().encode("utf-8")).hexdigest()
    return digest[:10]


def _conflict_key(candidate: VariantCandidate) -> str:
    if candidate.variant_id != "Unknown":
        return candidate.variant_id.lower()
    gene_key = candidate.gene.lower() if candidate.gene not in {"", "Unknown"} else "unknown"
    context = _context_hash(candidate.text_excerpt or f"{candidate.source_doc_id}:{candidate.chunk_id}")
    return f"{candidate.source_doc_id}:{gene_key}:{candidate.chunk_id}:{context}"


def _slice_excerpt(text: str, limit: int = 320) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _should_keep_variant_candidate(fields: Dict[str, str], metrics: List[MetricCandidate]) -> bool:
    return any(
        field not in {"", "Unknown"}
        for field in (
            fields["variant_id"],
            fields["hgvs"],
            fields["gene"],
            fields["clinvar_significance"],
            fields["phenotype"],
            fields["disease"],
        )
    ) or bool(metrics)


def _score_variant_candidate(fields: Dict[str, str], metrics: List[MetricCandidate], doc_type: str) -> Tuple[float, str]:
    score = 0.35
    reasons: List[str] = []
    if fields["variant_id"] != "Unknown" or fields["hgvs"] != "Unknown":
        score += 0.25
        reasons.append("variant id")
    if fields["gene"] != "Unknown":
        score += 0.15
        reasons.append("gene mention")
    if fields["clinvar_significance"] != "Unknown":
        score += 0.1
        reasons.append("clinvar classification")
    if metrics:
        score += 0.1
        reasons.append("metrics")
    if fields["ancestry"] != "Unknown":
        score += 0.05
        reasons.append("ancestry")
    if doc_type == "variant":
        score += 0.05
        reasons.append("variant doc")
    score = max(0.2, min(0.95, score))
    return score, ", ".join(reasons) or "baseline"


def _variant_contradictions(candidates: Sequence[VariantCandidate]) -> List[str]:
    notes: List[str] = []
    seen: Dict[str, set[str]] = {}
    representatives: Dict[str, VariantCandidate] = {}
    for candidate in candidates:
        if candidate.clinvar_significance == "Unknown":
            continue
        key = _conflict_key(candidate)
        seen.setdefault(key, set()).add(candidate.clinvar_significance)
        representatives.setdefault(key, candidate)
    for variant_key, labels in seen.items():
        if len(labels) > 1:
            rep = representatives.get(variant_key)
            if rep is None:
                continue
            if rep.variant_id != "Unknown":
                label = rep.variant_id
            elif rep.gene != "Unknown":
                label = f"{rep.gene} ({rep.source_doc_id})"
            else:
                label = f"{rep.source_doc_id} chunk {rep.chunk_id}"
            notes.append(f"Conflicting ClinVar significance for {label}: {', '.join(sorted(labels))}")
    return notes


def _extract_variant_fields(
    passage: Passage,
    variant_hint: Optional[str],
    phenotype_hint: Optional[str],
) -> Dict[str, object]:
    summary = passage.summary or ""
    text = passage.text or ""
    combined = f"{summary} {text}".strip()
    lowered = combined.lower()
    short_tokens = passage.short_tokens or []
    normalized = _normalize_hgvs_region(combined)
    hgvs_token = _first_match(VARIANT_ID_PATTERNS, normalized) or _first_match(HGVS_PROTEIN_PATTERNS, normalized)
    hgvs_value = _canonicalize_hgvs(hgvs_token)
    variant_value = variant_hint or (hgvs_value if hgvs_value != "Unknown" else "Unknown")
    gene = _detect_gene(combined)
    phenotype, disease = _detect_phenotype(lowered, phenotype_hint)
    cohort = _detect_cohort(lowered, short_tokens)
    ancestry = _detect_ancestry(lowered, short_tokens)
    case_count, control_count = _extract_case_control(lowered)
    clinvar_significance = _extract_clinvar_significance(lowered)
    gnomad_frequency = _extract_gnomad_frequency(lowered)
    return {
        "variant_id": variant_value,
        "hgvs": hgvs_value,
        "gene": gene,
        "phenotype": phenotype,
        "disease": disease,
        "cohort": cohort,
        "ancestry": ancestry,
        "case_count": case_count,
        "control_count": control_count,
        "clinvar_significance": clinvar_significance,
        "gnomad_frequency": gnomad_frequency,
    }


def assemble_variant_evidence(
    passages: Sequence[Passage],
    query: Optional[str] = None,
    variant_id: Optional[str] = None,
    phenotype: Optional[str] = None,
) -> VariantEvidenceBundle:
    query_terms = _query_terms(query)
    covered_terms: set[str] = set()
    candidates: List[VariantCandidate] = []
    telemetry_tokens: List[str] = []
    passages_list = list(passages)

    for passage in passages_list:
        searchable = f"{passage.summary or ''} {(passage.text or '')}".lower()
        for term in query_terms:
            if term in searchable:
                covered_terms.add(term)
        metrics = _metric_candidates_from_passage(passage)
        fields = _extract_variant_fields(passage, variant_id, phenotype)
        if not _should_keep_variant_candidate(fields, metrics):
            continue
        doc_type = getattr(passage, "doc_type", "paper") or "paper"
        short_hits = _short_token_hits(passage.short_tokens or [])
        if fields["ancestry"] == "Unknown" and short_hits:
            telemetry_tokens.extend(short_hits)
        confidence, reason = _score_variant_candidate(fields, metrics, doc_type)
        text_excerpt_source = passage.text or passage.summary or ""
        case_count = fields["case_count"] if isinstance(fields["case_count"], int) else None
        control_count = fields["control_count"] if isinstance(fields["control_count"], int) else None
        candidates.append(
            VariantCandidate(
                variant_id=_normalize_value(fields["variant_id"]),
                hgvs=_normalize_value(fields["hgvs"]),
                gene=_normalize_value(fields["gene"]),
                phenotype=_normalize_value(fields["phenotype"]),
                disease=_normalize_value(fields["disease"]),
                cohort=_normalize_value(fields["cohort"]),
                ancestry=_normalize_value(fields["ancestry"]),
                case_count=case_count,
                control_count=control_count,
                clinvar_significance=_normalize_value(fields["clinvar_significance"]),
                gnomad_frequency=_normalize_value(fields["gnomad_frequency"]),
                pathogenicity_metrics=metrics,
                chunk_id=passage.chunk_id,
                chunk_type=passage.chunk_type or ("table" if passage.is_table_or_figure else "body"),
                doc_type=doc_type,
                page=passage.page,
                source_doc_id=passage.doc_id,
                source_path=passage.source_path,
                text_excerpt=_slice_excerpt(text_excerpt_source.strip()),
                short_token_hits=short_hits,
                confidence=confidence,
                confidence_reason=reason,
            )
        )

    variant_mentions = sum(1 for cand in candidates if cand.variant_id != "Unknown" or cand.hgvs != "Unknown")
    ancestry_mentions = sum(1 for cand in candidates if cand.ancestry != "Unknown")
    phenotype_mentions = sum(1 for cand in candidates if cand.phenotype != "Unknown" or cand.disease != "Unknown")

    missing_fields: List[str] = []

    def _mark_missing(label: str) -> None:
        if label not in missing_fields:
            missing_fields.append(label)

    if variant_mentions == 0:
        _mark_missing("variant identifier")
    if variant_id and not any(variant_id.lower() in {cand.variant_id.lower(), cand.hgvs.lower()} for cand in candidates):
        _mark_missing("requested variant mention")
    if phenotype and phenotype_mentions == 0:
        _mark_missing("requested phenotype context")
    if ancestry_mentions == 0:
        _mark_missing("ancestry context")
    if not any(cand.clinvar_significance != "Unknown" for cand in candidates):
        _mark_missing("ClinVar classification")
    if not any(cand.case_count is not None for cand in candidates):
        _mark_missing("case counts")
    if not any(cand.control_count is not None for cand in candidates):
        _mark_missing("control counts")
    if not any(cand.gnomad_frequency != "Unknown" for cand in candidates):
        _mark_missing("population frequency")

    uncovered_requests = sorted(set(query_terms) - covered_terms)
    notes: List[str] = []
    if uncovered_requests:
        notes.append("Missing query terms: " + ", ".join(uncovered_requests))

    telemetry_tokens = sorted(set(token for token in telemetry_tokens if token))
    if telemetry_tokens and ancestry_mentions == 0:
        notes.append("Short-token hints observed (needs confirmation): " + ", ".join(telemetry_tokens))

    coverage = VariantCoverageReport(
        total_passages=len(passages_list),
        variant_candidates=len(candidates),
        ancestry_mentions=ancestry_mentions,
        phenotype_mentions=phenotype_mentions,
        missing_fields=missing_fields,
        uncovered_requests=uncovered_requests,
        notes=notes,
    )
    contradictions = _variant_contradictions(candidates)

    return VariantEvidenceBundle(passages=passages_list, candidates=candidates, coverage=coverage, contradictions=contradictions)


__all__ = [
    "MetricCandidate",
    "CoverageReport",
    "EvidenceBundle",
    "VariantCandidate",
    "VariantCoverageReport",
    "VariantEvidenceBundle",
    "assemble_paper_evidence",
    "assemble_variant_evidence",
]

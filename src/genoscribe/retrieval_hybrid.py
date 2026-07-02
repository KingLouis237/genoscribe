from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from genoscribe.corpus import load_manifest
from genoscribe.ingestion.metric_extractor import extract_metrics
from genoscribe.indexing.dense_index import DenseRetriever
from genoscribe.indexing.fusion import reciprocal_rank_fusion
from genoscribe.indexing.reranker import DenseReranker
from genoscribe.indexing.sparse_index import tokenize
from genoscribe.schemas.document import DocumentIndex, LibraryStats, Passage
from genoscribe.search.backends import SearchBackendRegistry, SearchRequest

MODE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "assembly": (
        "assembly",
        "busco",
        "quast",
        "kat",
        "bandage",
        "contig",
        "scaffold",
        "n50",
        "ng50",
    ),
    "variant": (
        "variant",
        "clinvar",
        "pathogenic",
        "mutation",
        "pllr",
        "esm1b",
        "dyna",
        "geno",
    ),
}

MODE_NEGATIVE_HINTS: Dict[str, Tuple[str, ...]] = {
    "assembly": ("clinvar", "variant", "mutation"),
    "variant": ("assembly", "busco", "quast"),
}

QUERY_STOPWORDS = {
    "analysis",
    "analyses",
    "bias",
    "result",
    "results",
    "study",
    "studies",
    "model",
    "models",
    "disease",
    "diseases",
}

SHORT_TOKEN_WHITELIST = {
    "cm",  # cardiomyopathy cohort
    "arm",  # arrhythmia cohort
    "vus",
    "afr",
    "eur",
    "pllr",
    "auc",
    "mcv",
}

FIGURE_INFO_THRESHOLD = 0.6
TARGET_DOC_BOOST = 1.25
NON_TARGET_PENALTY = 0.65
MODE_WEIGHT_MIN = 0.4
MODE_WEIGHT_MAX = 1.8
TARGET_RESCUE_OVERLAP_MIN = 0.2
TARGET_FALLBACK_MAX_NOISE = 0.55
SCOPED_TARGET_MIN_QUERY_OVERLAP = 0.3
SCOPED_TARGET_MAX_NOISE = 0.4
SCOPED_TARGET_MAX_SCORE_GAP = 0.05
SCOPED_TARGET_SEED_MAX = 2
SCOPED_TARGET_SEED_MIN_OVERLAP = 0.2
SCOPED_TARGET_SEED_MAX_NOISE = 0.5
SCOPED_TARGET_SEED_DOC_TYPE_MISMATCH_PENALTY = 0.12
SCOPED_TARGET_METRIC_INFO_FLOOR = 0.15
SCOPED_TARGET_METRIC_SEED_MAX = 2
SCOPED_TARGET_METRIC_SEED_MIN_OVERLAP = 0.1
SCOPED_TARGET_METRIC_SEED_MIN_METRIC_LABEL_OVERLAP = 0.2
SCOPED_TARGET_METRIC_SEED_MAX_NOISE = 0.5
SCOPED_TARGET_METRIC_SEED_DOC_TYPE_MISMATCH_PENALTY = 0.1

METRIC_QUERY_TERMS = {
    "metric",
    "metrics",
    "aupr",
    "auc",
    "auroc",
    "roc",
    "precision",
    "recall",
    "accuracy",
    "f1",
    "sensitivity",
    "specificity",
    "pvalue",
    "pvalues",
    "p",
    "kl",
    "divergence",
    "oddsratio",
    "odds",
    "ratio",
}

METRIC_SIGNAL_LABEL_KEYS = {
    "auc",
    "auroc",
    "aupr",
    "auprc",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "specificity",
    "sensitivity",
    "pvalue",
    "n50",
    "ng50",
    "busco",
    "completeness",
    "mcc",
    "oddsratio",
    "kl",
    "divergence",
}

METRIC_SIGNAL_TASK_KEYS = {
    "rocauc",
    "prauc",
    "precision",
    "recall",
    "accuracy",
    "f1",
    "significance",
    "kl",
    "assemblyqc",
    "threshold",
}

METRIC_SIGNAL_TEXT_RE = re.compile(
    r"\b(?:auc|auroc|aupr|accuracy|precision|recall|f1|p[\s-]*value|n50|ng50|busco|completeness|specificity|sensitivity|mcc|odds ratio|odds_ratio|kl divergence)\b",
    re.IGNORECASE,
)

RUNTIME_METRIC_SIGNAL_MIN_INFORMATIVE_OVERLAP = 0.2
BOILERPLATE_METRIC_PATTERNS = (
    re.compile(r"\bpage\s+\d+\s+of\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bopen\s+access\b", re.IGNORECASE),
    re.compile(r"\bthe\s+author\(s\)\b", re.IGNORECASE),
    re.compile(r"\bdeclarations?\b", re.IGNORECASE),
    re.compile(r"\bethics\s+approval\b", re.IGNORECASE),
    re.compile(r"\bconsent\s+to\s+participate\b", re.IGNORECASE),
    re.compile(r"\bcorrespondence\b", re.IGNORECASE),
    re.compile(r"\baffiliations?\b", re.IGNORECASE),
)

ALIAS_STOPWORDS = {
    "paper",
    "study",
    "article",
    "model",
    "models",
    "genomic",
    "genomics",
    "prediction",
    "predicting",
    "variant",
    "variants",
    "pathogenicity",
    "benchmark",
    "benchmarks",
}

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "corpus" / "corpus_manifest.json"
DEICTIC_SCOPE_PATTERN = re.compile(r"\bthis\b[\w\s-]{0,40}\bpaper\b", re.IGNORECASE)


@dataclass
class FilterDecision:
    passage: Passage
    fused_score: float
    mode_boost: float
    noise_penalty: float
    query_overlap: float
    informative_overlap: float
    query_weight: float
    duplicate_of: Optional[str]
    figure_quota_hit: bool
    kept: bool
    final_rank: Optional[int]
    chunk_type: str
    doc_type: str
    reason: str


def _fingerprint(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _effective_noise(passage: Passage) -> float:
    if passage.noise_level > 0:
        return passage.noise_level
    if not passage.is_table_or_figure and (passage.chunk_type not in {"caption", "figure_derived", "table", "mixed"}):
        return 0.0
    text = passage.text or ""
    if not text:
        return 0.0
    digits = sum(ch.isdigit() for ch in text)
    noise = digits / max(1, len(text))
    passage.noise_level = noise
    return noise


def _query_overlap_ratio(passage: Passage, query_terms: Optional[Sequence[str]]) -> float:
    if not query_terms:
        return 1.0
    terms = {term for term in query_terms if term}
    if not terms:
        return 1.0
    searchable = f"{(passage.summary or '')} {(passage.text or '')}".lower()
    if not searchable.strip():
        return 0.0
    hits = sum(1 for term in terms if term in searchable)
    return hits / len(terms)


def _is_figure_chunk(passage: Passage) -> bool:
    chunk_type = (passage.chunk_type or "").lower()
    return passage.is_table_or_figure or chunk_type in {"caption", "figure_derived", "table", "mixed"}


def _mode_context_ok(passage: Passage, mode: Optional[str]) -> bool:
    doc_type = (getattr(passage, "doc_type", "paper") or "paper").lower()
    if not mode or mode == "paper":
        return doc_type in {"paper", "unknown"}
    return doc_type == mode


def _informative_query_terms(query_terms: Optional[Sequence[str]], mode: Optional[str]) -> List[str]:
    if not query_terms:
        return []
    skip = {token for token in MODE_KEYWORDS.get(mode or "", ())}
    informative: List[str] = []
    for term in query_terms:
        if term in skip or term in QUERY_STOPWORDS:
            continue
        lowered = term.lower()
        if len(term) < 5 and lowered not in SHORT_TOKEN_WHITELIST:
            continue
        informative.append(term)
    return informative


def _normalize_token_key(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (token or "").lower())


def _is_metric_intent(query_terms: Optional[Sequence[str]]) -> bool:
    if not query_terms:
        return False
    normalized = {_normalize_token_key(term) for term in query_terms}
    return bool(normalized & METRIC_QUERY_TERMS)


def _metric_record_is_meaningful(record: Dict[str, str]) -> bool:
    label = str(record.get("label", "")).strip()
    task = str(record.get("task", "")).strip()
    value = str(record.get("value", "")).strip()
    context = str(record.get("context", "")).strip()
    if not label or not value:
        return False

    norm_label = _normalize_token_key(label)
    norm_task = _normalize_token_key(task)
    if not norm_label:
        return False

    metadata_label_markers = (
        "doi",
        "license",
        "copyright",
        "received",
        "accepted",
        "published",
        "pmid",
        "issn",
        "volume",
        "issue",
        "page",
        "pages",
    )
    if any(marker in norm_label for marker in metadata_label_markers):
        return False

    has_metric_key = any(token in norm_label for token in METRIC_SIGNAL_LABEL_KEYS) or any(
        token in norm_task for token in METRIC_SIGNAL_TASK_KEYS
    )
    if not has_metric_key:
        return False

    try:
        numeric = float(value)
    except ValueError:
        return False

    # Avoid treating publication metadata (years/pages) as quantitative metrics.
    if re.fullmatch(r"\d{4}", value) and 1800 <= int(value) <= 2100:
        return False

    metric_signature = f"{norm_label} {norm_task}"
    if "pvalue" in metric_signature and numeric > 1.0:
        return False
    bounded_metric_markers = (
        "auc",
        "auroc",
        "aupr",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "sensitivity",
        "specificity",
        "completeness",
    )
    if any(marker in metric_signature for marker in bounded_metric_markers) and numeric > 100.0:
        return False

    context_lower = context.lower()
    metadata_context_markers = ("doi", "http://", "https://", "license", "copyright", "pmid")
    if any(marker in context_lower for marker in metadata_context_markers) and not any(
        marker in metric_signature for marker in METRIC_SIGNAL_LABEL_KEYS
    ):
        return False
    return True


def _has_runtime_metric_signal(passage: Passage) -> bool:
    source_text = passage.raw_text or passage.text or ""
    if not source_text.strip():
        return False
    if not METRIC_SIGNAL_TEXT_RE.search(source_text):
        return False
    extracted = extract_metrics(source_text, page=passage.page)
    if not extracted:
        return False
    return any(_metric_record_is_meaningful(record) for record in extracted)


def _meaningful_metric_records(passage: Passage) -> List[Dict[str, str]]:
    return [record for record in (passage.metrics or []) if _metric_record_is_meaningful(record)]


def _looks_like_metric_boilerplate(passage: Passage) -> bool:
    text = (passage.summary or passage.text or "").strip()
    if not text:
        return True
    lower = text.lower()
    if all(pattern.search(text) for pattern in BOILERPLATE_METRIC_PATTERNS[:2]):
        return True
    for pattern in BOILERPLATE_METRIC_PATTERNS:
        if pattern.search(text):
            if len(lower) < 220:
                return True
            if "accuracy" not in lower and "precision" not in lower and "recall" not in lower and "auc" not in lower:
                return True
    metadata_markers = ("doi.org/", "not applicable", "received", "accepted", "published online")
    if any(marker in lower for marker in metadata_markers) and len(lower) < 260:
        return True
    return False


def _metric_label_overlap_ratio(passage: Passage, query_terms: Sequence[str]) -> float:
    query_metric_terms = {_normalize_token_key(term) for term in query_terms if _normalize_token_key(term) in METRIC_QUERY_TERMS}
    if not query_metric_terms:
        return 0.0
    label_terms: set[str] = set()
    for record in _meaningful_metric_records(passage):
        label_terms.add(_normalize_token_key(str(record.get("label", ""))))
        label_terms.add(_normalize_token_key(str(record.get("task", ""))))
    label_terms = {term for term in label_terms if term}
    if not label_terms:
        return 0.0
    hits = sum(1 for term in query_metric_terms if any(term in label for label in label_terms))
    return hits / len(query_metric_terms)


def _target_metric_seed_score(
    passage: Passage,
    *,
    query_terms: Sequence[str],
    informative_terms: Sequence[str],
    mode: Optional[str],
    runtime_metric_cache: Dict[str, bool],
) -> Optional[float]:
    query_overlap = _query_overlap_ratio(passage, query_terms)
    informative_overlap = _query_overlap_ratio(passage, informative_terms or None) if informative_terms else query_overlap
    if max(query_overlap, informative_overlap) < SCOPED_TARGET_METRIC_SEED_MIN_OVERLAP:
        return None
    noise = _effective_noise(passage)
    if noise > SCOPED_TARGET_METRIC_SEED_MAX_NOISE:
        return None
    if _looks_like_metric_boilerplate(passage):
        return None

    meaningful_metrics = _meaningful_metric_records(passage)
    key = f"{passage.doc_id}:{passage.chunk_id}"
    runtime_signal = runtime_metric_cache.setdefault(key, _has_runtime_metric_signal(passage))
    if not meaningful_metrics and not runtime_signal:
        return None

    metric_overlap = _metric_label_overlap_ratio(passage, query_terms)
    if query_overlap < SCOPED_TARGET_METRIC_SEED_MIN_OVERLAP and metric_overlap < SCOPED_TARGET_METRIC_SEED_MIN_METRIC_LABEL_OVERLAP:
        return None

    mode_context_ok = _mode_context_ok(passage, mode)
    chunk_type = (passage.chunk_type or "").lower()
    chunk_bonus = 0.0
    if chunk_type in {"body", "table"}:
        chunk_bonus = 0.05
    elif chunk_type in {"caption", "figure_derived"}:
        chunk_bonus = 0.02
    metric_strength = min(1.0, len(meaningful_metrics) / 3.0) if meaningful_metrics else 0.7
    score = (
        0.42 * query_overlap
        + 0.22 * informative_overlap
        + 0.24 * metric_strength
        + 0.12 * metric_overlap
        + chunk_bonus
    )
    score -= min(0.2, noise * 0.2)
    if not mode_context_ok:
        score -= SCOPED_TARGET_METRIC_SEED_DOC_TYPE_MISMATCH_PENALTY
    return score


def _qualifies_scoped_target_anchor(
    decision: FilterDecision,
    *,
    has_query_terms: bool,
) -> bool:
    if not has_query_terms:
        return False
    if decision.query_overlap < SCOPED_TARGET_MIN_QUERY_OVERLAP:
        return False
    if decision.noise_penalty > SCOPED_TARGET_MAX_NOISE:
        return False
    return True


def _strip_timestamp_suffix(stem: str) -> str:
    stripped = re.sub(r"[-_]\d{9,}$", "", stem)
    stripped = re.sub(r"[-_]20\d{2}[-_]\d{2}[-_]\d{2}(?:[-_]\d{2}[-_]\d{2}[-_]\d{2})?$", "", stripped)
    return stripped


def _extract_doi_tokens(text: str) -> List[str]:
    if not text:
        return []
    matches = re.findall(r"10\.\d{4,9}/[^\s\"'<>]+", text.lower())
    return [_normalize_alias(match) for match in matches]


def _doc_scope_aliases(doc: DocumentIndex) -> List[str]:
    aliases: List[str] = []
    stem = Path(doc.source_path).stem
    stem_base = _strip_timestamp_suffix(stem)
    title = getattr(doc, "title", "") or ""

    for raw in (doc.doc_id, stem_base, title):
        alias = _normalize_alias(raw)
        if len(alias) >= 4:
            aliases.append(alias)

    stem_head = stem_base.split("_", 1)[0]
    if re.fullmatch(r"[A-Za-z0-9]{3,12}", stem_head):
        aliases.append(_normalize_alias(stem_head))

    head_token = re.split(r"[-_]", stem_head)[0].lower()
    if len(head_token) >= 6 and head_token not in ALIAS_STOPWORDS:
        aliases.append(_normalize_alias(head_token))

    aliases.extend(_extract_doi_tokens(" ".join([doc.doc_id, stem, title])))
    return sorted({alias for alias in aliases if alias and alias not in ALIAS_STOPWORDS})


@lru_cache(maxsize=1)
def _manifest_scope_aliases_by_filename() -> Dict[str, Tuple[str, ...]]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        specs = load_manifest(MANIFEST_PATH)
    except Exception:
        return {}
    aliases: Dict[str, Tuple[str, ...]] = {}
    for spec in specs:
        filename = Path(spec.filename).name
        if not filename:
            continue
        scope_aliases = tuple(alias for alias in spec.scope_aliases if alias.strip())
        if scope_aliases:
            aliases[filename] = scope_aliases
    return aliases


def _manifest_scope_aliases_for_library(library: Sequence[DocumentIndex]) -> Dict[str, Tuple[str, ...]]:
    by_filename = _manifest_scope_aliases_by_filename()
    if not by_filename:
        return {}
    per_doc: Dict[str, Tuple[str, ...]] = {}
    for doc in library:
        filename = Path(doc.source_path).name
        aliases = by_filename.get(filename)
        if aliases:
            per_doc[doc.doc_id] = aliases
    return per_doc


def _query_tokens(query: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", query)
        if len(token) >= 3
    }


def _alias_matches_query(alias: str, normalized_query: str, query_tokens: set[str]) -> bool:
    normalized_alias = _normalize_alias(alias)
    if normalized_alias and normalized_alias in normalized_query:
        return True
    alias_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", alias)
        if len(token) >= 3
    }
    if alias_tokens and alias_tokens.issubset(query_tokens):
        return True
    return False


def _is_deictic_scoped_query(query: str) -> bool:
    return bool(DEICTIC_SCOPE_PATTERN.search(query or ""))


def _mode_weight(passage: Passage, mode: Optional[str]) -> Tuple[float, int, int]:
    if not mode or mode == "paper":
        # paper mode acts as baseline
        return 1.0, 0, 0
    hints = MODE_KEYWORDS.get(mode, ())
    penalties = MODE_NEGATIVE_HINTS.get(mode, ())
    searchable = f"{Path(passage.source_path).stem} {(passage.summary or passage.text or '')}".lower()
    hits = sum(1 for token in hints if token in searchable)
    neg_hits = sum(1 for token in penalties if token in searchable)
    if hits == 0:
        return (0.6 if mode != "paper" else 1.0), hits, neg_hits
    weight = min(1.4, 1.0 + 0.18 * hits)
    if neg_hits:
        weight -= min(0.3, 0.1 * neg_hits)
    doc_type = getattr(passage, "doc_type", "paper") or "paper"
    if doc_type != "paper":
        if doc_type == mode:
            weight += 0.2
        else:
            weight -= 0.25
    return max(0.4, min(1.6, weight)), hits, neg_hits


def _target_seed_score(
    passage: Passage,
    *,
    query_terms: Sequence[str],
    informative_terms: Sequence[str],
    mode: Optional[str],
) -> Optional[float]:
    mode_context_ok = _mode_context_ok(passage, mode)
    if not mode_context_ok and mode != "paper":
        return None
    overlap = _query_overlap_ratio(passage, query_terms)
    if overlap < SCOPED_TARGET_SEED_MIN_OVERLAP:
        return None
    informative_overlap = _query_overlap_ratio(passage, informative_terms or None) if informative_terms else overlap
    noise = _effective_noise(passage)
    if noise > SCOPED_TARGET_SEED_MAX_NOISE:
        return None
    figure_like = _is_figure_chunk(passage)
    has_metrics = bool(passage.metrics)
    if figure_like and (not has_metrics) and informative_overlap < FIGURE_INFO_THRESHOLD:
        return None
    score = 0.7 * overlap + 0.3 * informative_overlap
    if has_metrics:
        score += 0.03
    if not mode_context_ok:
        # Scoped target seeding is a narrow rescue path; apply a penalty instead of hard-rejecting
        # non-paper doc_type passages from the explicitly requested target document.
        score -= SCOPED_TARGET_SEED_DOC_TYPE_MISMATCH_PENALTY
    score -= min(0.2, noise * 0.2)
    return score


def _build_scoped_target_seed_slice(
    *,
    library: Sequence[DocumentIndex],
    target_doc_ids: Sequence[str],
    query_terms: Sequence[str],
    mode: Optional[str],
    top_k: int,
) -> List[Passage]:
    if mode != "paper" or not target_doc_ids or not query_terms:
        return []
    target_set = {doc_id for doc_id in target_doc_ids}
    informative_terms = _informative_query_terms(query_terms, mode)
    scored: List[Tuple[float, Passage]] = []
    for doc in library:
        if doc.doc_id not in target_set:
            continue
        for passage in doc.passages:
            score = _target_seed_score(
                passage,
                query_terms=query_terms,
                informative_terms=informative_terms,
                mode=mode,
            )
            if score is None:
                continue
            scored.append((score, passage))

    if not scored:
        return []

    scored.sort(key=lambda item: item[0], reverse=True)
    max_seed = min(SCOPED_TARGET_SEED_MAX, max(1, top_k))
    seeded: List[Passage] = []
    used_docs: set[str] = set()
    for _, passage in scored:
        # Keep seeded slice diverse across target docs when multiple targets are inferred.
        if passage.doc_id in used_docs:
            continue
        seeded.append(passage)
        used_docs.add(passage.doc_id)
        if len(seeded) >= max_seed:
            break

    if seeded:
        return seeded
    # If all high-ranked candidates came from a single target doc, allow one fallback from that same doc.
    return [scored[0][1]]


def _build_scoped_target_metric_seed_slice(
    *,
    library: Sequence[DocumentIndex],
    target_doc_ids: Sequence[str],
    query_terms: Sequence[str],
    mode: Optional[str],
    top_k: int,
    exclude_keys: Optional[set[str]] = None,
) -> List[Passage]:
    if mode != "paper" or not target_doc_ids or not query_terms:
        return []
    target_set = {doc_id for doc_id in target_doc_ids}
    informative_terms = _informative_query_terms(query_terms, mode)
    exclude = exclude_keys or set()
    runtime_metric_cache: Dict[str, bool] = {}
    scored: List[Tuple[float, Passage]] = []
    seen_fingerprints: set[str] = set()

    for doc in library:
        if doc.doc_id not in target_set:
            continue
        for passage in doc.passages:
            key = f"{passage.doc_id}:{passage.chunk_id}"
            if key in exclude:
                continue
            score = _target_metric_seed_score(
                passage,
                query_terms=query_terms,
                informative_terms=informative_terms,
                mode=mode,
                runtime_metric_cache=runtime_metric_cache,
            )
            if score is None:
                continue
            fingerprint = _fingerprint(passage.text or passage.summary or "")
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            scored.append((score, passage))

    if not scored:
        return []

    scored.sort(key=lambda item: item[0], reverse=True)
    max_seed = min(SCOPED_TARGET_METRIC_SEED_MAX, max(1, top_k))
    seeded = [passage for _, passage in scored[:max_seed]]
    return seeded


def filter_passages_for_quality(
    scored_passages: Sequence[Tuple[Passage, float]],
    top_k: int,
    mode: Optional[str] = None,
    query_terms: Optional[Sequence[str]] = None,
    target_doc_ids: Optional[Sequence[str]] = None,
) -> Tuple[List[Passage], List[FilterDecision]]:
    if top_k <= 0 or not scored_passages:
        return [], []

    ranked: List[Tuple[float, Passage]] = []
    decision_meta: Dict[str, FilterDecision] = {}
    informative_terms = _informative_query_terms(query_terms, mode)
    metric_intent = _is_metric_intent(query_terms)
    target_set = {doc_id for doc_id in target_doc_ids or []}
    scoped_metric_target = mode == "paper" and metric_intent and bool(target_set)
    runtime_metric_cache: Dict[str, bool] = {}
    runtime_metric_support: Dict[str, bool] = {}
    prefer_targets = bool(target_set) and any(passage.doc_id in target_set for passage, _ in scored_passages)
    for passage, raw_score in scored_passages:
        noise = _effective_noise(passage)
        figure_like = _is_figure_chunk(passage)
        figure_penalty = 0.15 if figure_like else 0.0
        if figure_like and not passage.metrics:
            figure_penalty += 0.1
        penalty = min(0.85, noise * 0.8 + figure_penalty)
        mode_weight, _, _ = _mode_weight(passage, mode)
        if prefer_targets:
            if passage.doc_id in target_set:
                mode_weight *= TARGET_DOC_BOOST
            else:
                mode_weight *= NON_TARGET_PENALTY
            mode_weight = max(MODE_WEIGHT_MIN, min(MODE_WEIGHT_MAX, mode_weight))
        overlap = _query_overlap_ratio(passage, query_terms)
        informative_overlap = _query_overlap_ratio(passage, informative_terms or None)
        if query_terms:
            if overlap == 0.0:
                query_weight = 0.1
            else:
                query_weight = 0.4 + 0.6 * overlap
        else:
            query_weight = 1.0
        adjusted = raw_score * mode_weight * (1 - penalty) * query_weight
        key = f"{passage.doc_id}:{passage.chunk_id}"
        decision = FilterDecision(
            passage=passage,
            fused_score=adjusted,
            mode_boost=mode_weight,
            noise_penalty=penalty,
            query_overlap=overlap,
            informative_overlap=informative_overlap,
            query_weight=query_weight,
            duplicate_of=None,
            figure_quota_hit=False,
            kept=False,
            final_rank=None,
            chunk_type=passage.chunk_type or ("table" if passage.is_table_or_figure else "body"),
            doc_type=getattr(passage, "doc_type", "paper") or "paper",
            reason="",
        )
        decision_meta[key] = decision
        doc_type = (getattr(passage, "doc_type", "paper") or "paper").lower()
        figure_has_metrics = bool(passage.metrics)
        runtime_metric_signal = False
        if scoped_metric_target and passage.doc_id in target_set and figure_like and not figure_has_metrics:
            if (
                overlap >= SCOPED_TARGET_MIN_QUERY_OVERLAP
                and decision.noise_penalty <= SCOPED_TARGET_MAX_NOISE
                and (
                    (not informative_terms and overlap >= TARGET_RESCUE_OVERLAP_MIN)
                    or informative_overlap >= RUNTIME_METRIC_SIGNAL_MIN_INFORMATIVE_OVERLAP
                )
            ):
                runtime_metric_signal = runtime_metric_cache.setdefault(key, _has_runtime_metric_signal(passage))
        figure_has_metrics_effective = figure_has_metrics or runtime_metric_signal
        runtime_metric_support[key] = runtime_metric_signal
        mode_context_ok = _mode_context_ok(passage, mode)

        if figure_like:
            if not figure_has_metrics and runtime_metric_signal:
                # Scoped paper-mode metric intent path already enforces target, relevance, and noise thresholds.
                # Do not route these through the doc_type/mode gate used for pre-extracted figure metrics.
                pass
            elif not figure_has_metrics_effective:
                strong_overlap = informative_overlap >= FIGURE_INFO_THRESHOLD if informative_terms else False
                overlap_ok = overlap >= FIGURE_INFO_THRESHOLD
                if not (passage.doc_id in target_set and (strong_overlap or overlap_ok)):
                    decision.reason = "dropped: figure lacks structured metrics"
                    continue
            else:
                strong_overlap = informative_overlap >= FIGURE_INFO_THRESHOLD if informative_terms else False
                scoped_target_metric_override = (
                    scoped_metric_target
                    and passage.doc_id in target_set
                    and overlap >= SCOPED_TARGET_MIN_QUERY_OVERLAP
                    and decision.noise_penalty <= SCOPED_TARGET_MAX_NOISE
                    and informative_overlap >= SCOPED_TARGET_METRIC_INFO_FLOOR
                )
                if not (strong_overlap or mode_context_ok or scoped_target_metric_override):
                    decision.reason = "dropped: figure lacks informative overlap"
                    continue

        if informative_terms and informative_overlap == 0.0:
            scoped_target_override = (
                passage.doc_id in target_set
                and _qualifies_scoped_target_anchor(
                    decision,
                    has_query_terms=bool(query_terms),
                )
            )
            has_metric_support = bool(passage.metrics) or runtime_metric_signal
            if not scoped_target_override and not (metric_intent and has_metric_support and overlap > 0.0):
                decision.reason = "dropped: no informative-term overlap"
                continue
        if query_terms and overlap == 0.0:
            decision.reason = "dropped: no query overlap"
            continue
        ranked.append((adjusted, passage))

    ranked.sort(key=lambda item: item[0], reverse=True)
    filtered: List[Passage] = []
    seen: set[str] = set()
    dedup_map: Dict[str, str] = {}
    doc_counts: Dict[str, int] = defaultdict(int)
    figure_counts: Dict[str, int] = defaultdict(int)
    per_doc_limit = max(2, top_k // 2)

    for _, passage in ranked:
        meta_key = f"{passage.doc_id}:{passage.chunk_id}"
        decision = decision_meta[meta_key]
        fingerprint = _fingerprint(passage.text or passage.summary or "")
        if fingerprint in seen:
            decision.duplicate_of = dedup_map.get(fingerprint)
            decision.reason = "dropped: duplicate fingerprint"
            continue
        if doc_counts[passage.doc_id] >= per_doc_limit:
            decision.reason = "dropped: per-doc quota reached"
            continue
        if _is_figure_chunk(passage):
            meta_key = f"{passage.doc_id}:{passage.chunk_id}"
            has_metric_support = bool(passage.metrics) or runtime_metric_support.get(meta_key, False)
            if figure_counts[passage.doc_id] >= 1 and not has_metric_support:
                decision.figure_quota_hit = True
                decision.reason = "dropped: figure quota without metrics"
                continue
            figure_counts[passage.doc_id] += 1
        seen.add(fingerprint)
        dedup_map[fingerprint] = meta_key
        filtered.append(passage)
        doc_counts[passage.doc_id] += 1
        decision.kept = True
        decision.final_rank = len(filtered)
        decision.reason = (
            f"kept: fused_score={decision.fused_score:.3f}, "
            f"mode_boost={decision.mode_boost:.2f}, "
            f"noise_penalty={decision.noise_penalty:.2f}, "
            f"query_weight={decision.query_weight:.2f}, "
            f"overlap={decision.query_overlap:.2f}, "
            f"info_overlap={decision.informative_overlap:.2f}"
        )
        if len(filtered) >= top_k:
            break

    def _current_kept_keys() -> set[str]:
        return {f"{p.doc_id}:{p.chunk_id}" for p in filtered}

    def _refresh_final_ranks() -> None:
        for info in decision_meta.values():
            if info.kept:
                info.final_rank = None
        for idx, passage in enumerate(filtered, start=1):
            key = f"{passage.doc_id}:{passage.chunk_id}"
            decision_meta[key].final_rank = idx

    def _replace_or_append(candidate_key: str, reason: str, replace_idx: Optional[int] = None) -> None:
        candidate = decision_meta[candidate_key]
        if candidate.kept:
            return
        if replace_idx is not None and 0 <= replace_idx < len(filtered):
            removed = filtered[replace_idx]
            removed_key = f"{removed.doc_id}:{removed.chunk_id}"
            removed_decision = decision_meta[removed_key]
            removed_decision.kept = False
            removed_decision.final_rank = None
            removed_decision.reason = f"dropped: replaced by {candidate_key}"
            filtered[replace_idx] = candidate.passage
        elif len(filtered) < top_k:
            filtered.append(candidate.passage)
        else:
            return
        candidate.kept = True
        candidate.reason = reason

    # Scoped target rescue: if targets exist but none survived, try to promote one target candidate.
    if target_set and filtered and not any(passage.doc_id in target_set for passage in filtered):
        weakest_non_target_idx: Optional[int] = None
        weakest_non_target_score: Optional[float] = None
        for idx, kept_passage in enumerate(filtered):
            if kept_passage.doc_id in target_set:
                continue
            kept_key = f"{kept_passage.doc_id}:{kept_passage.chunk_id}"
            kept_score = decision_meta[kept_key].fused_score
            if weakest_non_target_score is None or kept_score < weakest_non_target_score:
                weakest_non_target_idx = idx
                weakest_non_target_score = kept_score
        if weakest_non_target_idx is None or weakest_non_target_score is None:
            weakest_non_target_idx = len(filtered) - 1 if filtered else None
            if weakest_non_target_idx is not None:
                weakest_key = f"{filtered[weakest_non_target_idx].doc_id}:{filtered[weakest_non_target_idx].chunk_id}"
                weakest_non_target_score = decision_meta[weakest_key].fused_score

        kept_keys = _current_kept_keys()
        for _, passage in ranked:
            key = f"{passage.doc_id}:{passage.chunk_id}"
            decision = decision_meta[key]
            if key in kept_keys or passage.doc_id not in target_set:
                continue
            qualified = (
                _qualifies_scoped_target_anchor(decision, has_query_terms=bool(query_terms))
                or decision.informative_overlap >= TARGET_RESCUE_OVERLAP_MIN
                or (metric_intent and bool(passage.metrics))
            )
            if not qualified:
                continue
            if weakest_non_target_score is not None and (
                decision.fused_score + SCOPED_TARGET_MAX_SCORE_GAP < weakest_non_target_score
            ):
                continue
            _replace_or_append(
                key,
                "kept: target-doc anchor rescue within bounded score margin",
                replace_idx=weakest_non_target_idx,
            )
            break

    # Scoped fallback: if filtering emptied everything, keep one clean target passage for grounded scoped answers.
    if target_set and not filtered:
        for _, passage in ranked:
            key = f"{passage.doc_id}:{passage.chunk_id}"
            decision = decision_meta[key]
            if passage.doc_id not in target_set:
                continue
            if decision.noise_penalty > TARGET_FALLBACK_MAX_NOISE:
                continue
            if _is_figure_chunk(passage) and not passage.metrics:
                continue
            _replace_or_append(key, "kept: target-doc fallback after strict filtering")
            break

    # Metric-intent rescue: ensure at least one metric-bearing passage survives when available.
    def _supports_metric_intent(passage: Passage) -> bool:
        key = f"{passage.doc_id}:{passage.chunk_id}"
        return bool(passage.metrics) or runtime_metric_support.get(key, False)

    if metric_intent and filtered and not any(_supports_metric_intent(p) for p in filtered):
        kept_keys = _current_kept_keys()
        for _, passage in ranked:
            key = f"{passage.doc_id}:{passage.chunk_id}"
            decision = decision_meta[key]
            if key in kept_keys or not _supports_metric_intent(passage):
                continue
            if decision.query_overlap <= 0.0 and decision.informative_overlap <= 0.0:
                continue
            _replace_or_append(key, "kept: metric-intent rescue", replace_idx=len(filtered) - 1)
            break

    _refresh_final_ranks()
    for info in decision_meta.values():
        if not info.kept and not info.reason:
            info.reason = "dropped: below top-k threshold"
    decisions = list(decision_meta.values())
    return filtered, decisions


def infer_target_doc_ids(query: str, library: Sequence[DocumentIndex]) -> List[str]:
    if not query or not library:
        return []
    normalized_query = _normalize_alias(query)
    query_tokens = _query_tokens(query)
    query_dois = set(_extract_doi_tokens(query))
    manifest_aliases = _manifest_scope_aliases_for_library(library)
    deictic_query = _is_deictic_scoped_query(query)
    candidates: List[Tuple[str, bool]] = []
    for doc in library:
        strong_match = False
        weak_match = False

        doc_aliases = _doc_scope_aliases(doc)
        alias_set = set(doc_aliases)
        if query_dois and alias_set & query_dois:
            strong_match = True

        curated_aliases = manifest_aliases.get(doc.doc_id, ())
        if curated_aliases:
            if any(_alias_matches_query(alias, normalized_query, query_tokens) for alias in curated_aliases):
                strong_match = True

        title_alias = _normalize_alias(getattr(doc, "title", "") or "")
        if len(title_alias) >= 8 and title_alias in normalized_query:
            strong_match = True

        if not strong_match:
            weak_match = any(len(alias) >= 4 and alias in normalized_query for alias in doc_aliases)

        if strong_match or weak_match:
            candidates.append((doc.doc_id, strong_match))

    if deictic_query:
        strong_targets = sorted({doc_id for doc_id, is_strong in candidates if is_strong})
        if strong_targets:
            return strong_targets
        return []

    return sorted({doc_id for doc_id, _ in candidates})


def _normalize_alias(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def hybrid_collect(
    *,
    library: List[DocumentIndex],
    stats: Optional[LibraryStats],
    query: str,
    search_method: str,
    search_registry: SearchBackendRegistry,
    dense_retriever: DenseRetriever,
    reranker: DenseReranker,
    mode: Optional[str] = None,
    base_passages: Optional[List[Passage]] = None,
    top_k: int = 6,
    target_doc_ids: Optional[Sequence[str]] = None,
    return_decisions: bool = False,
) -> Tuple[List[Passage], Dict[str, float], Dict[str, List[Passage]]] | Tuple[
    List[Passage], Dict[str, float], Dict[str, List[Passage]], List[FilterDecision]
]:
    timings: Dict[str, float] = {}
    runs: List[List[Passage]] = []
    stage_hits: Dict[str, List[Passage]] = {}
    query_terms = tokenize(query)

    if base_passages:
        runs.append(base_passages[:])
        stage_hits["seed"] = base_passages[:]

    targets = list(target_doc_ids or infer_target_doc_ids(query, library))

    if stats:
        backend = search_registry.get(search_method)
        start = time.perf_counter()
        primary_hits = backend.search(
            library=library,
            stats=stats,
            request=SearchRequest(query=query, top_k=top_k),
        )
        timings["sparse_primary_ms"] = (time.perf_counter() - start) * 1000
        stage_hits["primary"] = primary_hits
        if primary_hits:
            runs.append(primary_hits)

        fallback_method = "bm25" if search_method != "bm25" else "tfidf"
        if fallback_method != search_method:
            fallback_backend = search_registry.get(fallback_method)
            start = time.perf_counter()
            fallback_hits = fallback_backend.search(
                library=library,
                stats=stats,
                request=SearchRequest(query=query, top_k=top_k),
            )
            timings["sparse_fallback_ms"] = (time.perf_counter() - start) * 1000
            stage_hits["fallback"] = fallback_hits
            if fallback_hits:
                runs.append(fallback_hits)
    else:
        timings.setdefault("sparse_primary_ms", 0.0)
        timings.setdefault("sparse_fallback_ms", 0.0)
        stage_hits["primary"] = []
        stage_hits["fallback"] = []

    dense_stats: Dict[str, float] = {}
    dense_pairs = dense_retriever.search(query, top_k=top_k, timings=dense_stats)
    timings["dense_ms"] = dense_stats.get("dense_total_ms", timings.get("dense_ms", 0.0))
    timings.update(dense_stats)
    dense_hits = [p for p, _ in dense_pairs]
    stage_hits["dense"] = dense_hits
    if dense_hits:
        runs.append(dense_hits)

    target_set = {doc_id for doc_id in targets}
    metric_intent = mode == "paper" and _is_metric_intent(query_terms)
    if mode == "paper" and target_set:
        initial_pools: List[Passage] = []
        for stage_name in ("seed", "primary", "fallback", "dense"):
            initial_pools.extend(stage_hits.get(stage_name, []))
        has_target_upstream = any(passage.doc_id in target_set for passage in initial_pools)
        if not has_target_upstream:
            target_seed = _build_scoped_target_seed_slice(
                library=library,
                target_doc_ids=targets,
                query_terms=query_terms,
                mode=mode,
                top_k=top_k,
            )
            stage_hits["target_seed"] = target_seed
            if target_seed:
                runs.append(target_seed)
        if metric_intent:
            initial_keys = {f"{passage.doc_id}:{passage.chunk_id}" for passage in initial_pools}
            metric_seed = _build_scoped_target_metric_seed_slice(
                library=library,
                target_doc_ids=targets,
                query_terms=query_terms,
                mode=mode,
                top_k=min(SCOPED_TARGET_METRIC_SEED_MAX, top_k),
                exclude_keys=initial_keys,
            )
            if metric_seed:
                stage_hits["target_metric_seed"] = metric_seed

    fused: List[Passage] = []
    start = time.perf_counter()
    if runs:
        fused = runs[0] if len(runs) == 1 else reciprocal_rank_fusion(runs)
    timings["fusion_ms"] = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    rerank_source = fused or base_passages or []
    target_metric_seed = stage_hits.get("target_metric_seed", [])
    if target_metric_seed:
        seeded_source = list(rerank_source)
        seen_keys = {f"{passage.doc_id}:{passage.chunk_id}" for passage in seeded_source}
        for passage in target_metric_seed:
            key = f"{passage.doc_id}:{passage.chunk_id}"
            if key in seen_keys:
                continue
            seeded_source.append(passage)
            seen_keys.add(key)
        # Metric seeds are appended only to rerank input (not fusion) so they can compete
        # without dominating ranking stages automatically.
        rerank_source = seeded_source
    rerank_limit = top_k * 2
    if targets:
        rerank_limit = max(rerank_limit, top_k * 3)
    scored = reranker.rerank(rerank_source, query, top_k=rerank_limit)
    timings["rerank_ms"] = (time.perf_counter() - start) * 1000
    stage_hits["reranked"] = [p for p, _ in scored]

    start = time.perf_counter()
    filtered, decisions = filter_passages_for_quality(
        scored,
        top_k,
        mode=mode,
        query_terms=query_terms,
        target_doc_ids=targets,
    )
    timings["quality_filter_ms"] = (time.perf_counter() - start) * 1000
    stage_hits["final"] = filtered
    if return_decisions:
        return filtered, timings, stage_hits, decisions
    return filtered, timings, stage_hits


__all__ = ["hybrid_collect", "filter_passages_for_quality", "FilterDecision", "infer_target_doc_ids"]

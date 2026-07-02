from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

VALUE_PATTERN = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"

LABEL_VALUE_RE = re.compile(
    rf"(?P<label>[A-Za-z][A-Za-z0-9 %/\-]{{1,40}})\s*(?:=|:)\s*(?P<value>{VALUE_PATTERN})(?P<unit>%|[A-Za-z]+)?",
    re.IGNORECASE,
)
P_VALUE_RE = re.compile(rf"\b(p\s*(?:value)?)[^=]*=\s*(?P<value>{VALUE_PATTERN})", re.IGNORECASE)
CONTEXT_WINDOW = 160

MODEL_KEYWORDS = {
    "dyna": "DYNA",
    "esm1b": "ESM1b",
    "esm2": "ESM2",
    "shine": "SHINE",
    "bart": "BART",
    "xgboost": "XGBoost",
    "adaboost": "AdaBoost",
    "m-cap": "M-CAP",
    "revel": "REVEL",
    "hyenadna": "HyenaDNA",
    "genalm": "GenaLM",
    "nucleotide transformer": "Nucleotide Transformer",
    "nt": "Nucleotide Transformer",
    "varcopp": "VarCoPP",
    "snpred": "SNPred",
    "metarnn": "MetaRNN",
}

DATASET_KEYWORDS = {
    "clinvar cm": "ClinVar CM",
    "clinvar arm": "ClinVar ARM",
    "cm cohort": "ClinVar CM",
    "arm cohort": "ClinVar ARM",
    "cm genes": "ClinVar CM",
    "arm genes": "ClinVar ARM",
    "cardiomyopathy": "ClinVar CM",
    "arrhythmia": "ClinVar ARM",
    "shine": "SHINE benchmark",
    "varcopp": "VarCoPP cohort",
    "gnomad": "gnomAD",
    "exac": "ExAC",
}

TASK_KEYWORDS = [
    ("aupr", "PR-AUC"),
    ("auc", "ROC-AUC"),
    ("kl divergence", "KL divergence"),
    ("precision", "Precision"),
    ("recall", "Recall"),
    ("p-value", "Significance"),
    ("busco", "Assembly QC"),
]

JUNK_LABEL_PATTERNS = [
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\bdoi\b", re.IGNORECASE),
    re.compile(r"\barxiv\b", re.IGNORECASE),
    re.compile(r"\bpreprint\b", re.IGNORECASE),
    re.compile(r"\blicense\b", re.IGNORECASE),
]

SHORT_LABEL_ALLOWLIST = {
    "auc",
    "auroc",
    "aupr",
    "auprc",
    "mcc",
    "f1",
    "ppv",
    "npv",
    "roc",
}

VARCOPP_SS_RE = re.compile(r"(?:support[^A-Za-z0-9]{0,10})?SS\s*=\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
VARCOPP_CS_RE = re.compile(r"(?:classification\s+score|CS)\s*(?:=|>=)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
VARCOPP_CONFIDENCE_RE = re.compile(
    r"(?P<zone>9[59])%\s+confidence\s+zone.*?CS\s*(?:>=|=)\s*(?P<cs>\d+(?:\.\d+)?).*?SS\s*(?:>=|=)\s*(?P<ss>\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
SHINE_BALANCED_RE = re.compile(
    r"balanced accuracy (?:scores?|score)\s+of\s+(\d+(?:\.\d+)?)\s*(?:and|,)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
SHINE_AUC_RE = re.compile(r"AUC value of\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
TABLE_DECIMAL_RE = re.compile(r"-?\d+\.\d+(?:e-?\d+)?", re.IGNORECASE)
TABLE_ROW_BLOCK_TERMS = ("model", "method", "tool", "system")
TABLE_HEADER_MIN_COLUMNS = 2


@dataclass(frozen=True)
class _TableMetricColumn:
    label: str
    task: str
    start: int
    end: int


TABLE_HEADER_VARIANTS: Sequence[Tuple[str, str, str]] = (
    ("accuracy", "Accuracy", "Accuracy"),
    ("precision", "Precision", "Precision"),
    ("recall", "Recall", "Recall"),
    ("f1 score", "F1", "F1"),
    ("f1", "F1", "F1"),
    ("auroc", "AUROC", "ROC-AUC"),
    ("aupr", "AUPR", "PR-AUC"),
    ("roc auc", "ROC AUC", "ROC-AUC"),
    ("auc roc", "ROC AUC", "ROC-AUC"),
    ("pr auc", "PR AUC", "PR-AUC"),
    ("auc pr", "PR AUC", "PR-AUC"),
    ("auc", "AUC", "ROC-AUC"),
)


def _structured_metric(
    *,
    label: str,
    value: str,
    unit: str = "",
    text: str = "",
    model: str = "Unknown",
    dataset: str = "Unknown",
    task: str = "Unknown",
    panel: str = "",
    page: Optional[int] = None,
    context: str = "",
) -> Dict[str, str]:
    return {
        "label": label or "Unknown",
        "value": value or "",
        "unit": unit or "",
        "text": text or "",
        "model": model or "Unknown",
        "dataset": dataset or "Unknown",
        "task": task or "Unknown",
        "panel": panel or "",
        "page": page if page is not None else "",
        "context": context or "",
    }


def _context_window(text: str, start: int, end: int) -> str:
    s = max(0, start - CONTEXT_WINDOW)
    e = min(len(text), end + CONTEXT_WINDOW)
    return text[s:e]


def _match_from_keywords(window: str, mapping: Dict[str, str], label_hint: str = "") -> str:
    lowered = window.lower()
    hint = label_hint.lower()
    ordered = sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True)
    if hint:
        for key, label in ordered:
            if key in hint:
                return label
    for key, label in ordered:
        if key in lowered:
            return label
    return ""


def _infer_task(label: str, window: str) -> str:
    lowered = label.lower()
    window_lower = window.lower()
    for keyword, task in TASK_KEYWORDS:
        if keyword in lowered:
            return task
    for keyword, task in TASK_KEYWORDS:
        if keyword in window_lower:
            return task
    return ""


def _detect_panel(text: str, start: int) -> str:
    lookback = text[max(0, start - 120) : start].lower()
    fig_match = re.search(r"figure\s*\d+[^a-z0-9]*([a-k])", lookback)
    if fig_match:
        return fig_match.group(1).upper()
    lines = lookback.splitlines()
    if lines:
        candidate = lines[-1].strip()
        if len(candidate) == 1 and candidate in "abcdefghijk":
            return candidate.upper()
    return ""


def _dataset_from_context(label: str, window: str) -> str:
    dataset = _match_from_keywords(window, DATASET_KEYWORDS, label)
    if dataset:
        return dataset
    upper = window.upper()
    if ("CLINVAR" in upper or "CARDIOMYOPATH" in upper) and re.search(r"\bCM\b", upper):
        return "ClinVar CM"
    if ("CLINVAR" in upper or "ARRHYTHM" in upper) and re.search(r"\bARM\b", upper):
        return "ClinVar ARM"
    return ""


def _build_context_payload(
    text: str,
    match: re.Match[str],
    page: Optional[int],
    label: str,
) -> Dict[str, str | int]:
    window = _context_window(text, match.start(), match.end())
    return {
        "model": _match_from_keywords(window, MODEL_KEYWORDS, label),
        "dataset": _dataset_from_context(label, window),
        "task": _infer_task(label, window),
        "panel": _detect_panel(text, match.start()),
        "page": page if page is not None else "",
        "context": window.strip(),
    }


def _normalize_label(label: str) -> str:
    cleaned = re.sub(r"\s+", " ", label).strip(" :=")
    if cleaned.lower() in {"p", "p value"}:
        return "p-value"
    return cleaned


def _normalize_table_line(line: str) -> str:
    normalized = line.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _extract_table_columns(header_line: str) -> List[_TableMetricColumn]:
    header = _normalize_table_line(header_line)
    lower = header.lower()
    if not any(term in lower for term in TABLE_ROW_BLOCK_TERMS):
        return []

    matches: List[_TableMetricColumn] = []
    ordered_variants = sorted(TABLE_HEADER_VARIANTS, key=lambda item: len(item[0]), reverse=True)
    for variant, label, task in ordered_variants:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])", re.IGNORECASE)
        for match in pattern.finditer(lower):
            matches.append(
                _TableMetricColumn(
                    label=label,
                    task=task,
                    start=match.start(),
                    end=match.end(),
                )
            )
    if not matches:
        return []

    matches.sort(key=lambda item: (item.start, -(item.end - item.start)))
    selected: List[_TableMetricColumn] = []
    for column in matches:
        if selected and column.start < selected[-1].end:
            continue
        selected.append(column)

    deduped: List[_TableMetricColumn] = []
    seen: set[Tuple[int, int, str]] = set()
    for column in selected:
        key = (column.start, column.end, column.label)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(column)
    return deduped


def _extract_table_block_metrics(text: str, page: Optional[int]) -> List[Dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    metrics: List[Dict[str, str]] = []
    idx = 0
    while idx < len(lines):
        header_line = lines[idx]
        columns = _extract_table_columns(header_line)
        if len(columns) < TABLE_HEADER_MIN_COLUMNS:
            idx += 1
            continue

        parsed_rows = 0
        row_idx = idx + 1
        while row_idx < len(lines):
            row = _normalize_table_line(lines[row_idx])
            if not row:
                row_idx += 1
                continue
            decimals = list(TABLE_DECIMAL_RE.finditer(row))
            metric_count = len(columns)
            if len(decimals) < max(TABLE_HEADER_MIN_COLUMNS, metric_count):
                # Stop at first non-row once we have consumed a contiguous table section.
                if parsed_rows > 0:
                    break
                row_idx += 1
                continue
            selected_values = decimals[-metric_count:]
            first_value_start = selected_values[0].start()
            model_name = row[:first_value_start].strip(" |-:\t")
            if not model_name or len(model_name) < 2:
                if parsed_rows > 0:
                    break
                row_idx += 1
                continue

            row_context = f"{header_line} {row}"
            dataset = _dataset_from_context(" ".join(col.label for col in columns), row_context) or "Unknown"
            for column, value_match in zip(columns, selected_values):
                value = value_match.group(0)
                metrics.append(
                    _structured_metric(
                        label=column.label,
                        value=value,
                        model=model_name,
                        dataset=dataset,
                        task=column.task or "Unknown",
                        page=page,
                        context=row_context,
                    )
                )
            parsed_rows += 1
            row_idx += 1

        idx = row_idx if parsed_rows else idx + 1
    return metrics


def _looks_like_metric_label(label: str) -> bool:
    lowered = label.lower()
    if not any(ch.isalpha() for ch in label):
        return False
    if any(pattern.search(lowered) for pattern in JUNK_LABEL_PATTERNS):
        return False
    if label.count("/") >= 2:
        return False
    if lowered.startswith(("of ", "and ")):
        return False
    words = re.findall(r"[A-Za-z]+", label)
    if not words:
        return False
    has_meaningful = any(len(word) >= 3 for word in words)
    if not has_meaningful and not any(word.lower() in SHORT_LABEL_ALLOWLIST for word in words):
        return False
    return True


def extract_metrics(text: str, *, page: Optional[int] = None) -> List[Dict[str, str]]:
    metrics: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _append(record: Dict[str, str]) -> None:
        structured = _structured_metric(
            label=record.get("label", "Unknown"),
            value=record.get("value", ""),
            unit=record.get("unit", ""),
            text=record.get("text", ""),
            model=record.get("model", "Unknown"),
            dataset=record.get("dataset", "Unknown"),
            task=record.get("task", "Unknown"),
            panel=record.get("panel", ""),
            page=record.get("page"),
            context=record.get("context", ""),
        )
        key = (structured["label"].lower(), structured["value"])
        if key in seen:
            return
        seen.add(key)
        metrics.append(structured)

    for record in _extract_varcopp_metrics(text, page):
        _append(record)
    for record in _extract_shine_metrics(text, page):
        _append(record)
    for record in _extract_table_block_metrics(text, page):
        _append(record)

    for match in LABEL_VALUE_RE.finditer(text):
        label = _normalize_label(match.group("label"))
        if not _looks_like_metric_label(label):
            continue
        if not any(c.isalpha() for c in label):
            continue
        prefix = text[max(0, match.start() - 12) : match.start()].lower()
        if "doi" in prefix or "://" in prefix:
            continue
        if match.start() > 0 and text[match.start() - 1] == "/":
            continue
        value = match.group("value")
        unit = (match.group("unit") or "").strip()
        context = _build_context_payload(text, match, page, label)
        model = context["model"] or "Unknown"
        dataset = context["dataset"] or "Unknown"
        task = context["task"] or "Unknown"
        _append(
            {
                "label": label,
                "value": value,
                "unit": unit,
                "text": match.group(0).strip(),
                "model": model,
                "dataset": dataset,
                "task": task,
                "panel": context["panel"],
                "page": context["page"],
                "context": context["context"],
            }
        )

    for match in P_VALUE_RE.finditer(text):
        label = _normalize_label(match.group(1))
        value = match.group("value")
        context = _build_context_payload(text, match, page, label)
        model = context["model"] or "Unknown"
        dataset = context["dataset"] or "Unknown"
        _append(
            {
                "label": label,
                "value": value,
                "unit": "",
                "text": match.group(0).strip(),
                "model": model,
                "dataset": dataset,
                "task": context["task"] or "Significance",
                "panel": context["panel"],
                "page": context["page"],
                "context": context["context"],
            }
        )

    return metrics


def _extract_varcopp_metrics(text: str, page: Optional[int]) -> List[Dict[str, str]]:
    lowered = text.lower()
    if "varcopp" not in lowered:
        return []
    results: List[Dict[str, str]] = []
    idx = 1
    for match in VARCOPP_SS_RE.finditer(text):
        prefix = text[max(0, match.start() - 20) : match.start()].lower()
        if "support" not in prefix and "ss" not in prefix:
            continue
        label = f"VarCoPP SS #{idx}"
        idx += 1
        results.append(
            _structured_metric(
                label=label,
                value=match.group(1),
                model="VarCoPP",
                dataset="VarCoPP cohort",
                task="Support Score",
                page=page,
                context=match.group(0).strip(),
            )
        )
    cs_idx = 1
    for match in VARCOPP_CS_RE.finditer(text):
        label = f"VarCoPP CS #{cs_idx}"
        cs_idx += 1
        results.append(
            _structured_metric(
                label=label,
                value=match.group(1),
                model="VarCoPP",
                dataset="VarCoPP cohort",
                task="Classification Score",
                page=page,
                context=match.group(0).strip(),
            )
        )
    for match in VARCOPP_CONFIDENCE_RE.finditer(text):
        zone = match.group("zone")
        cs_val = match.group("cs")
        ss_val = match.group("ss")
        context = match.group(0).strip()
        if cs_val:
            results.append(
                _structured_metric(
                    label=f"VarCoPP CS threshold ({zone}% zone)",
                    value=cs_val,
                    model="VarCoPP",
                    dataset="VarCoPP cohort",
                    task="Threshold",
                    page=page,
                    context=context,
                )
            )
        if ss_val:
            results.append(
                _structured_metric(
                    label=f"VarCoPP SS threshold ({zone}% zone)",
                    value=ss_val,
                    model="VarCoPP",
                    dataset="VarCoPP cohort",
                    task="Threshold",
                    page=page,
                    context=context,
                )
            )
    return results


def _extract_shine_metrics(text: str, page: Optional[int]) -> List[Dict[str, str]]:
    lowered = text.lower()
    if "shine" not in lowered:
        return []
    results: List[Dict[str, str]] = []
    for match in SHINE_BALANCED_RE.finditer(text):
        tail = text[match.end() : match.end() + 80].lower()
        first_label = "SHINE balanced accuracy"
        second_label = "SHINE balanced accuracy"
        if "deletion" in tail:
            first_label += " (deletions)"
        if "insertion" in tail:
            second_label += " (insertions)"
        results.append(
            _structured_metric(
                label=first_label,
                value=match.group(1),
                model="SHINE",
                dataset="Unknown",
                task="Balanced Accuracy",
                page=page,
                context=match.group(0).strip(),
            )
        )
        results.append(
            _structured_metric(
                label=second_label,
                value=match.group(2),
                model="SHINE",
                dataset="Unknown",
                task="Balanced Accuracy",
                page=page,
                context=match.group(0).strip(),
            )
        )
    for match in SHINE_AUC_RE.finditer(text):
        segment = text[max(0, match.start() - 40) : match.end() + 40].lower()
        label = "SHINE AUC"
        if "deletion" in segment:
            label += " (deletions)"
        elif "insertion" in segment:
            label += " (insertions)"
        results.append(
            _structured_metric(
                label=label,
                value=match.group(1),
                model="SHINE",
                dataset="Unknown",
                task="ROC-AUC",
                page=page,
                context=match.group(0).strip(),
            )
        )
    return results


__all__ = ["extract_metrics"]

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ALLOWED_BUCKETS = {
    "core_benchmark",
    "generalization",
    "stress_test",
    "mode_specific",
    "anti_overfitting",
}

ALLOWED_MODES = {"paper", "assembly", "variant"}


def _norm_tag(tag: str) -> str:
    return tag.strip().lower().replace("-", "_").replace(" ", "_")


@dataclass(frozen=True)
class CorpusDocumentSpec:
    slug: str
    title: str
    filename: str
    buckets: Tuple[str, ...]
    modes: Tuple[str, ...]
    scope_aliases: Tuple[str, ...] = ()
    source_url: str | None = None
    notes: str = ""
    expected_doc_type: str | None = None


@dataclass(frozen=True)
class CorpusDocumentStatus:
    spec: CorpusDocumentSpec
    file_present: bool
    indexed_doc_ids: Tuple[str, ...]


def load_manifest(path: Path) -> List[CorpusDocumentSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    docs = payload.get("documents")
    if not isinstance(docs, list):
        raise ValueError("Manifest must contain a 'documents' list.")

    specs: List[CorpusDocumentSpec] = []
    seen_slugs: set[str] = set()
    seen_scope_aliases: Dict[str, str] = {}
    for row in docs:
        if not isinstance(row, dict):
            raise ValueError("Each manifest entry must be an object.")

        slug = str(row.get("slug", "")).strip()
        title = str(row.get("title", "")).strip()
        filename = str(row.get("filename", "")).strip()
        if not slug or not title or not filename:
            raise ValueError(f"Entry missing required fields: {row}")
        if slug in seen_slugs:
            raise ValueError(f"Duplicate slug in manifest: {slug}")
        seen_slugs.add(slug)

        buckets = tuple(sorted({_norm_tag(tag) for tag in row.get("buckets", [])}))
        unknown_buckets = [tag for tag in buckets if tag not in ALLOWED_BUCKETS]
        if unknown_buckets:
            raise ValueError(f"Unknown buckets for {slug}: {unknown_buckets}")

        modes = tuple(sorted({_norm_tag(tag) for tag in row.get("modes", [])}))
        unknown_modes = [tag for tag in modes if tag not in ALLOWED_MODES]
        if unknown_modes:
            raise ValueError(f"Unknown modes for {slug}: {unknown_modes}")

        raw_scope_aliases = row.get("scope_aliases", [])
        if raw_scope_aliases is None:
            raw_scope_aliases = []
        if not isinstance(raw_scope_aliases, list):
            raise ValueError(f"scope_aliases for {slug} must be a list when provided.")
        scope_aliases = tuple(sorted({str(alias).strip() for alias in raw_scope_aliases if str(alias).strip()}))
        for alias in scope_aliases:
            norm_alias = _norm_tag(alias)
            existing_slug = seen_scope_aliases.get(norm_alias)
            if existing_slug and existing_slug != slug:
                raise ValueError(
                    f"Duplicate scope_alias '{alias}' for {slug}; already used by {existing_slug}."
                )
            seen_scope_aliases[norm_alias] = slug

        source_url = row.get("source_url")
        if source_url is not None:
            source_url = str(source_url).strip() or None

        specs.append(
            CorpusDocumentSpec(
                slug=slug,
                title=title,
                filename=filename,
                buckets=buckets,
                modes=modes,
                scope_aliases=scope_aliases,
                source_url=source_url,
                notes=str(row.get("notes", "")).strip(),
                expected_doc_type=row.get("expected_doc_type"),
            )
        )
    return specs


def summarize_specs(specs: Iterable[CorpusDocumentSpec]) -> Dict[str, Dict[str, int]]:
    bucket_counts: Dict[str, int] = {key: 0 for key in sorted(ALLOWED_BUCKETS)}
    mode_counts: Dict[str, int] = {key: 0 for key in sorted(ALLOWED_MODES)}
    for spec in specs:
        for bucket in spec.buckets:
            bucket_counts[bucket] += 1
        for mode in spec.modes:
            mode_counts[mode] += 1
    return {"buckets": bucket_counts, "modes": mode_counts}


def map_indexed_doc_ids_by_filename(library: Iterable[object]) -> Dict[str, List[str]]:
    indexed: Dict[str, List[str]] = {}
    for doc in library:
        source_path = getattr(doc, "source_path", "")
        if not source_path:
            continue
        filename = Path(source_path).name
        indexed.setdefault(filename, []).append(getattr(doc, "doc_id", ""))
    return indexed


def build_status(
    *,
    specs: Iterable[CorpusDocumentSpec],
    library_files_dir: Path,
    indexed_doc_ids_by_filename: Dict[str, List[str]],
) -> List[CorpusDocumentStatus]:
    rows: List[CorpusDocumentStatus] = []
    for spec in specs:
        rows.append(
            CorpusDocumentStatus(
                spec=spec,
                file_present=(library_files_dir / spec.filename).exists(),
                indexed_doc_ids=tuple(indexed_doc_ids_by_filename.get(spec.filename, [])),
            )
        )
    return rows

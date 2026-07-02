from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from pathlib import Path
from rich.console import Console

from genoscribe.config import LIBRARY_DIR, STATS_FILE, STATE_FILE
from genoscribe.schemas.document import DocumentIndex, LibraryStats, Passage

from ..indexing.sparse_index import calculate_avg_doc_length, calculate_idf, tf_vector, tokenize
from ..ingestion.chunk_typing import classify_chunk
from ..ingestion.doc_classifier import infer_document_type

console = Console()
_LIBRARY_REPAIRED = False


@dataclass
class AssistantState:
    working_notes: List[str]
    last_retrievals: List[Passage]
    watch_downloads_enabled: bool = False
    recent_doc_ids: List[str] = field(default_factory=list)
    first_run_checklist: Dict[str, bool] = field(
        default_factory=lambda: {"imported": False, "searched": False, "cited": False}
    )
    last_query: str = ""


def now_ts() -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S")


def save_doc_index(di: DocumentIndex) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    out = LIBRARY_DIR / f"{di.doc_id}.json"
    payload = {
        "doc_id": di.doc_id,
        "source_path": di.source_path,
        "ext": di.ext,
        "title": di.title,
        "doc_type": di.doc_type,
        "passages": [asdict(p) for p in di.passages],
        "vectors": di.vectors,
        "term_counts": di.term_counts,
        "doc_lengths": di.doc_lengths,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _recompute_passage_features(doc: DocumentIndex) -> bool:
    repaired = False
    if len(doc.term_counts) != len(doc.passages) or len(doc.doc_lengths) != len(doc.passages):
        doc.term_counts = []
        doc.doc_lengths = []
        for passage in doc.passages:
            toks = tokenize(passage.text)
            doc.doc_lengths.append(len(toks))
            counts: Dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            doc.term_counts.append(counts)
        repaired = True

    if len(doc.vectors) != len(doc.passages):
        doc.vectors = [tf_vector(p.text) for p in doc.passages]
        repaired = True

    chunk_updates = False
    for passage in doc.passages:
        if not passage.chunk_type or passage.chunk_type == "unknown":
            chunk_type = classify_chunk(
                raw_text=passage.raw_text or passage.text,
                clean_text=passage.text,
                is_table_or_figure=passage.is_table_or_figure,
                noise_level=passage.noise_level if hasattr(passage, "noise_level") else None,
            )
            passage.chunk_type = chunk_type
            chunk_updates = True
    if chunk_updates:
        repaired = True

    sample_texts = [(p.summary or p.text or "") for p in doc.passages[:8]]
    inferred_type = infer_document_type(
        source_name=Path(doc.source_path).stem if doc.source_path else doc.doc_id,
        title=doc.title,
        sample_texts=sample_texts,
    )
    current_type = getattr(doc, "doc_type", "paper") or "paper"
    doc.doc_type = current_type
    if inferred_type != current_type:
        doc.doc_type = inferred_type
        repaired = True
    for passage in doc.passages:
        if getattr(passage, "doc_type", doc.doc_type) != doc.doc_type:
            passage.doc_type = doc.doc_type
            repaired = True
    return repaired


def load_library() -> List[DocumentIndex]:
    global _LIBRARY_REPAIRED
    library: List[DocumentIndex] = []
    for fp in sorted(LIBRARY_DIR.glob("*.json")):
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
            passages = [Passage(**p) for p in obj["passages"]]
            doc = DocumentIndex(
                doc_id=obj["doc_id"],
                source_path=obj["source_path"],
                ext=obj["ext"],
                title=obj.get("title"),
                passages=passages,
                vectors=obj.get("vectors", []),
                term_counts=obj.get("term_counts", []),
                doc_lengths=obj.get("doc_lengths", []),
                doc_type=obj.get("doc_type", "paper"),
            )
            for passage in doc.passages:
                if not getattr(passage, "doc_type", None):
                    passage.doc_type = doc.doc_type
            library.append(doc)
            if _recompute_passage_features(doc):
                _LIBRARY_REPAIRED = True
                save_doc_index(doc)
        except Exception as exc:
            console.print(f"[yellow]Warning: Failed to load {fp.name}: {exc}[/yellow]")
            continue
    return library


def library_requires_stats_rebuild() -> bool:
    global _LIBRARY_REPAIRED
    needs_rebuild = _LIBRARY_REPAIRED
    _LIBRARY_REPAIRED = False
    return needs_rebuild


def save_library_stats(stats: LibraryStats) -> None:
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(stats)
    STATS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_library_stats() -> Optional[LibraryStats]:
    if not STATS_FILE.exists():
        return None
    try:
        obj = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        return LibraryStats(**obj)
    except Exception:
        return None


def rebuild_library_stats(library: List[DocumentIndex]) -> LibraryStats:
    console.print("[yellow]Calculating IDF weights...[/yellow]")
    idf_weights = calculate_idf(library)

    console.print("[yellow]Calculating average document length...[/yellow]")
    avg_doc_length = calculate_avg_doc_length(library)
    total_passages = sum(len(doc.passages) for doc in library)

    stats = LibraryStats(
        idf_weights=idf_weights,
        avg_doc_length=avg_doc_length,
        total_docs=len(library),
        total_passages=total_passages,
        last_updated=now_ts(),
    )
    save_library_stats(stats)
    console.print(
        f"[green]? Library stats updated:[/green] {len(library)} docs, {total_passages} passages, {len(idf_weights)} unique terms"
    )
    return stats


def save_state(state: AssistantState) -> None:
    payload = {
        "working_notes": state.working_notes,
        "last_retrievals": [asdict(p) for p in state.last_retrievals],
        "watch_downloads_enabled": state.watch_downloads_enabled,
        "recent_doc_ids": state.recent_doc_ids,
        "first_run_checklist": state.first_run_checklist,
        "last_query": state.last_query,
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> AssistantState:
    if not STATE_FILE.exists():
        return AssistantState(working_notes=[], last_retrievals=[])
    try:
        obj = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        checklist_default = {"imported": False, "searched": False, "cited": False}
        stored_checklist = obj.get("first_run_checklist") or {}
        return AssistantState(
            working_notes=obj.get("working_notes", []),
            last_retrievals=[Passage(**p) for p in obj.get("last_retrievals", [])],
            watch_downloads_enabled=obj.get("watch_downloads_enabled", False),
            recent_doc_ids=obj.get("recent_doc_ids", []),
            first_run_checklist={
                **checklist_default,
                **{k: bool(v) for k, v in stored_checklist.items() if k in checklist_default},
            },
            last_query=obj.get("last_query", ""),
        )
    except Exception:
        return AssistantState(working_notes=[], last_retrievals=[])


__all__ = [
    "AssistantState",
    "save_doc_index",
    "load_library",
    "library_requires_stats_rebuild",
    "save_library_stats",
    "load_library_stats",
    "rebuild_library_stats",
    "save_state",
    "load_state",
]

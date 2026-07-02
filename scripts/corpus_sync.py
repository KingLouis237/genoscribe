from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.request import Request, urlopen

from rich.console import Console
from rich.table import Table

from genoscribe.config import LIBRARY_FILES_DIR, OUTPUT_DIR
from genoscribe.corpus import (
    CorpusDocumentSpec,
    build_status,
    load_manifest,
    map_indexed_doc_ids_by_filename,
    summarize_specs,
)
from genoscribe.indexing import build_index_for_file
from genoscribe.storage.provenance_store import (
    load_library,
    load_library_stats,
    rebuild_library_stats,
    save_doc_index,
)

console = Console()


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download_pdf(url: str, destination: Path, timeout_s: int = 120) -> Tuple[int, str, int]:
    request = Request(
        url,
        headers={
            "User-Agent": "GenoScribeCorpusSync/1.0 (+local evidence review pipeline)",
            "Accept": "application/pdf,*/*",
        },
    )
    with urlopen(request, timeout=timeout_s) as response:
        status = getattr(response, "status", response.getcode())
        content_type = response.headers.get("Content-Type", "")
        payload = response.read()
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    if "pdf" not in content_type.lower() and not payload.startswith(b"%PDF"):
        raise RuntimeError(f"Unexpected content-type for {url}: {content_type}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=str(destination.parent), suffix=".tmp") as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(destination)
    return status, content_type, len(payload)


def _render_status_table(rows) -> None:
    table = Table(show_lines=True, title="Corpus sync status")
    table.add_column("Slug")
    table.add_column("File")
    table.add_column("Buckets")
    table.add_column("Modes")
    table.add_column("On disk")
    table.add_column("Indexed docs")
    for row in rows:
        table.add_row(
            row.spec.slug,
            row.spec.filename,
            ",".join(row.spec.buckets),
            ",".join(row.spec.modes),
            "yes" if row.file_present else "no",
            str(len(row.indexed_doc_ids)),
        )
    console.print(table)


def _serialize_status(row) -> Dict[str, object]:
    spec: CorpusDocumentSpec = row.spec
    return {
        "slug": spec.slug,
        "title": spec.title,
        "filename": spec.filename,
        "source_url": spec.source_url,
        "buckets": list(spec.buckets),
        "modes": list(spec.modes),
        "notes": spec.notes,
        "file_present": row.file_present,
        "indexed_doc_ids": list(row.indexed_doc_ids),
    }


def sync_corpus(*, manifest_path: Path, download_missing: bool, ingest_missing: bool) -> Path:
    specs = load_manifest(manifest_path)
    summary = summarize_specs(specs)
    library = load_library()
    indexed_by_file = map_indexed_doc_ids_by_filename(library)
    status_rows = build_status(
        specs=specs,
        library_files_dir=LIBRARY_FILES_DIR,
        indexed_doc_ids_by_filename=indexed_by_file,
    )
    _render_status_table(status_rows)

    stats = load_library_stats()
    if not stats:
        stats = rebuild_library_stats(library)

    actions: Dict[str, List[Dict[str, object]]] = {
        "downloaded": [],
        "ingested": [],
        "skipped": [],
        "failed": [],
    }

    for row in status_rows:
        spec = row.spec
        target_file = LIBRARY_FILES_DIR / spec.filename

        file_present = row.file_present
        indexed_ids = list(row.indexed_doc_ids)

        if not file_present and spec.source_url and download_missing:
            console.print(f"[cyan]Downloading[/cyan] {spec.slug} -> {target_file.name}")
            try:
                status_code, content_type, byte_size = _download_pdf(spec.source_url, target_file)
                file_present = True
                actions["downloaded"].append(
                    {
                        "slug": spec.slug,
                        "filename": spec.filename,
                        "url": spec.source_url,
                        "status_code": status_code,
                        "content_type": content_type,
                        "bytes": byte_size,
                        "sha256": _sha256(target_file.read_bytes()),
                    }
                )
            except Exception as exc:
                actions["failed"].append(
                    {
                        "slug": spec.slug,
                        "filename": spec.filename,
                        "stage": "download",
                        "error": str(exc),
                    }
                )
                continue
        elif not file_present and not spec.source_url:
            actions["skipped"].append(
                {
                    "slug": spec.slug,
                    "filename": spec.filename,
                    "reason": "missing file and no source_url in manifest",
                }
            )
            continue

        needs_ingest = file_present and not indexed_ids
        if needs_ingest and ingest_missing:
            console.print(f"[cyan]Indexing[/cyan] {spec.slug} ({target_file.name})")
            try:
                di = build_index_for_file(target_file, stats.idf_weights)
                save_doc_index(di)
                library.append(di)
                indexed_ids = [di.doc_id]
                actions["ingested"].append(
                    {
                        "slug": spec.slug,
                        "filename": spec.filename,
                        "doc_id": di.doc_id,
                        "passages": len(di.passages),
                        "doc_type": di.doc_type,
                    }
                )
            except Exception as exc:
                actions["failed"].append(
                    {
                        "slug": spec.slug,
                        "filename": spec.filename,
                        "stage": "ingest",
                        "error": str(exc),
                    }
                )
        elif not needs_ingest:
            actions["skipped"].append(
                {
                    "slug": spec.slug,
                    "filename": spec.filename,
                    "reason": "already indexed",
                    "indexed_doc_ids": indexed_ids,
                }
            )

    if actions["ingested"]:
        stats = rebuild_library_stats(library)

    refreshed_indexed = map_indexed_doc_ids_by_filename(library)
    refreshed_rows = build_status(
        specs=specs,
        library_files_dir=LIBRARY_FILES_DIR,
        indexed_doc_ids_by_filename=refreshed_indexed,
    )

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "summary": summary,
        "actions": actions,
        "final_status": [_serialize_status(row) for row in refreshed_rows],
        "library_stats": {
            "total_docs": stats.total_docs,
            "total_passages": stats.total_passages,
            "avg_doc_length": stats.avg_doc_length,
        },
        "flags": {
            "download_missing": download_missing,
            "ingest_missing": ingest_missing,
        },
    }

    out_dir = OUTPUT_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"corpus_inventory_{_now_stamp()}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync curated corpus entries into GenoScribe library.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/corpus/corpus_manifest.json"),
        help="Path to curated corpus manifest JSON.",
    )
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="Download missing files for entries that define source_url.",
    )
    parser.add_argument(
        "--ingest-missing",
        action="store_true",
        help="Index entries that exist on disk but are not yet in the library JSON store.",
    )
    args = parser.parse_args()

    out_path = sync_corpus(
        manifest_path=args.manifest,
        download_missing=args.download_missing,
        ingest_missing=args.ingest_missing,
    )
    console.print(f"[green]Saved corpus inventory report:[/green] {out_path}")


if __name__ == "__main__":
    main()

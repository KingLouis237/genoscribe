from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from genoscribe.config import LIBRARY_DIR, LIBRARY_FILES_DIR
from genoscribe.indexing import build_index_for_file
from genoscribe.storage.provenance_store import load_library, rebuild_library_stats, save_doc_index

console = Console()

DEMO_SOURCE = Path("docs/examples/demo_paper.md")
DEMO_FILENAME = "genoscribe_demo_paper.md"
DEMO_DOC_ID = "genoscribe_demo_paper"


def _apply_stable_demo_id(doc_index) -> None:
    doc_index.doc_id = DEMO_DOC_ID
    for passage in doc_index.passages:
        passage.doc_id = DEMO_DOC_ID
        for metric in passage.metrics:
            metric["source_doc_id"] = DEMO_DOC_ID


def build_demo_corpus() -> Path:
    if not DEMO_SOURCE.exists():
        raise FileNotFoundError(f"Missing demo source: {DEMO_SOURCE}")

    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_FILES_DIR.mkdir(parents=True, exist_ok=True)

    target = LIBRARY_FILES_DIR / DEMO_FILENAME
    shutil.copyfile(DEMO_SOURCE, target)

    library = [doc for doc in load_library() if doc.doc_id != DEMO_DOC_ID]
    stats = rebuild_library_stats(library)
    doc_index = build_index_for_file(target, stats.idf_weights)
    _apply_stable_demo_id(doc_index)
    save_doc_index(doc_index)

    refreshed = [doc for doc in load_library() if doc.doc_id != DEMO_DOC_ID]
    refreshed.append(doc_index)
    rebuild_library_stats(refreshed)

    console.print("[green]Demo corpus ready.[/green]")
    console.print(f"Indexed demo document: {DEMO_DOC_ID}")
    console.print(f"Local source copy: {target}")
    console.print("")
    console.print("Next commands:")
    console.print("  uv run streamlit run scripts/review_gui_streamlit.py")
    console.print(
        "  uv run python scripts/paper_validation_harness.py "
        "--matrix docs/examples/demo_validation_matrix.json "
        "--manifest docs/examples/demo_manifest.json --top-k 4"
    )
    return target


def main() -> None:
    build_demo_corpus()


if __name__ == "__main__":
    main()

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

from genoscribe.config import CHUNK_MAX_SIZE, CHUNK_OVERLAP_PARAS, CHUNK_TARGET_SIZE
from genoscribe.schemas.document import DocumentIndex, Passage

from ..ingestion.abbrev_utils import extract_short_tokens
from ..ingestion.chunk_typing import classify_chunk
from ..ingestion.doc_classifier import infer_document_type
from ..ingestion.metric_extractor import extract_metrics
from ..ingestion.metadata import infer_title
from ..ingestion.parser_pdf import read_pdf
from ..ingestion.parser_text import read_text
from ..ingestion.sectionizer import chunk_text
from ..ingestion.table_figure_extractor import build_passage_summary, strip_figure_noise
from .sparse_index import tfidf_vector, tokenize


def _chunk_iterator(text: str) -> List[str]:
    return chunk_text(
        text,
        target_size=CHUNK_TARGET_SIZE,
        max_size=CHUNK_MAX_SIZE,
        overlap_paras=CHUNK_OVERLAP_PARAS,
    )


def build_index_for_file(path: Path, idf_weights: Dict[str, float]) -> DocumentIndex:
    ext = path.suffix.lower()
    doc_id = f"{path.stem}-{int(time.time())}"

    passages: List[Passage] = []
    vectors: List[Dict[str, float]] = []
    term_counts: List[Dict[str, int]] = []
    doc_lengths: List[int] = []

    def _record_chunk(raw_chunk: str, page: Optional[int]) -> None:
        is_special = raw_chunk.startswith("[TABLE/FIGURE]")
        chunk = raw_chunk.replace("[TABLE/FIGURE]\n", "", 1) if is_special else raw_chunk

        clean_chunk, noise_level = strip_figure_noise(chunk, is_special)
        clean_chunk = clean_chunk or chunk
        passage_summary = build_passage_summary(clean_chunk, is_special)
        chunk_index = len(passages)
        metrics = extract_metrics(clean_chunk, page=page)
        for metric in metrics:
            metric["chunk_id"] = chunk_index
            metric["source_doc_id"] = doc_id
            metric["source_path"] = str(path)
        short_tokens = extract_short_tokens(clean_chunk)
        chunk_type = classify_chunk(
            raw_text=chunk,
            clean_text=clean_chunk,
            is_table_or_figure=is_special,
            noise_level=noise_level,
        )

        passage = Passage(
            doc_id=doc_id,
            source_path=str(path),
            page=page,
            chunk_id=chunk_index,
            text=clean_chunk,
            is_table_or_figure=is_special,
            raw_text=chunk,
            summary=passage_summary,
            noise_level=noise_level,
            metrics=metrics,
            chunk_type=chunk_type,
            short_tokens=short_tokens,
        )
        passages.append(passage)

        toks = tokenize(clean_chunk)
        doc_lengths.append(len(toks))
        term_count: Dict[str, int] = {}
        for t in toks:
            term_count[t] = term_count.get(t, 0) + 1
        term_counts.append(term_count)
        vectors.append(tfidf_vector(clean_chunk, idf_weights))

    if ext == ".pdf":
        pages = read_pdf(path)
        for page_no, page_text in pages:
            for chunk in _chunk_iterator(page_text):
                _record_chunk(chunk, page_no)
        title = infer_title(path, pages[0][1] if pages else path.stem)
    elif ext in {".txt", ".md"}:
        full = read_text(path)
        title = infer_title(path, full[:400])
        for chunk in _chunk_iterator(full):
            _record_chunk(chunk, None)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

    doc_type = infer_document_type(
        source_name=path.stem,
        title=title,
        sample_texts=[(p.summary or p.text or "") for p in passages[:8]],
    )
    for passage in passages:
        passage.doc_type = doc_type

    return DocumentIndex(
        doc_id=doc_id,
        source_path=str(path),
        ext=ext,
        title=title,
        passages=passages,
        vectors=vectors,
        term_counts=term_counts,
        doc_lengths=doc_lengths,
        doc_type=doc_type,
    )


__all__ = ["build_index_for_file"]

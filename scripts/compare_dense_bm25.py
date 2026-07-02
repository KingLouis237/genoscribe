import argparse
import json
import math
import re
from pathlib import Path

from genoscribe._config import BM25_B, BM25_K1, DATA_DIR
from genoscribe.schemas.document import DocumentIndex, Passage
from genoscribe.indexing.dense_index import DenseRetriever


def tokenize(text: str) -> list[str]:
    return [tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if len(tok) > 2]


def load_library() -> list[DocumentIndex]:
    library_dir = DATA_DIR / "library"
    documents: list[DocumentIndex] = []
    for fp in sorted(library_dir.glob("*.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        passages = [Passage(**p) for p in data["passages"]]
        doc = DocumentIndex(
            doc_id=data["doc_id"],
            source_path=data["source_path"],
            ext=data["ext"],
            title=data.get("title") or "",
            passages=passages,
            vectors=data.get("vectors", []),
            term_counts=data.get("term_counts", []),
            doc_lengths=data.get("doc_lengths", []),
            doc_type=data.get("doc_type", "paper"),
        )
        for passage in doc.passages:
            if not getattr(passage, "doc_type", None):
                passage.doc_type = doc.doc_type
        documents.append(doc)
    return documents


def load_stats() -> tuple[dict[str, float], float]:
    stats_path = DATA_DIR / "library_stats.json"
    obj = json.loads(stats_path.read_text(encoding="utf-8"))
    return obj["idf_weights"], obj["avg_doc_length"]


def bm25_search(library: list[DocumentIndex], query: str, idf: dict[str, float], avg_doc_len: float, top_k: int) -> list[tuple[Passage, float]]:
    query_terms = tokenize(query)
    scored: list[tuple[Passage, float]] = []
    for doc in library:
        for term_count, doc_len, passage in zip(doc.term_counts, doc.doc_lengths, doc.passages):
            score = 0.0
            for term in query_terms:
                tf = term_count.get(term)
                if not tf:
                    continue
                idf_val = idf.get(term, 0.0)
                numerator = tf * (BM25_K1 + 1)
                denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * (doc_len / (avg_doc_len or 1.0)))
                score += idf_val * (numerator / denominator)
            if score > 0:
                scored.append((passage, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare BM25 vs dense retriever results for a query.")
    parser.add_argument("--query", default="PLLR pathogenicity DYNA")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    library = load_library()
    idf, avg_doc_len = load_stats()

    bm25_hits = bm25_search(library, args.query, idf, avg_doc_len, args.top_k)
    print("BM25 top hits:")
    for passage, score in bm25_hits:
        preview = (passage.summary or passage.text).replace("\n", " ")[:90]
        print(f"- {passage.doc_id}:{passage.chunk_id} score={score:.3f} :: {preview}")

    retriever = DenseRetriever()
    retriever.index(library)
    dense_hits = retriever.search(args.query, top_k=args.top_k)
    print(f"\nDense top hits (n={len(dense_hits)}):")
    for passage, score in dense_hits:
        preview = (passage.summary or passage.text).replace("\n", " ")[:90]
        print(f"- {passage.doc_id}:{passage.chunk_id} score={score:.3f} :: {preview}")
    if not dense_hits:
        print("(no dense hits returned)")


if __name__ == "__main__":
    main()

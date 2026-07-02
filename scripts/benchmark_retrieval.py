import argparse
import time

from genoscribe.indexing.dense_index import DenseRetriever
from genoscribe.storage.provenance_store import load_library


def benchmark(query: str, top_k: int) -> None:
    library = load_library()
    retriever = DenseRetriever()

    t0 = time.perf_counter()
    retriever.index(library)
    index_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    hits = retriever.search(query, top_k=top_k)
    query_time = time.perf_counter() - t1

    print(f"Dense indexing time: {index_time:.2f}s for {sum(len(doc.passages) for doc in library)} passages")
    print(f"Query latency: {query_time*1000:.1f} ms for '{query}'")
    print("Top results:")
    for passage, score in hits:
        title = passage.source_path.split("\\")[-1]
        print(f"- {passage.doc_id}:{passage.chunk_id} (score={score:.3f}) :: {title}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark GenoScribe dense retrieval pipeline.")
    parser.add_argument("--query", default="PLLR pathogenicity DYNA", help="Query string to test.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of hits to display.")
    args = parser.parse_args()
    benchmark(args.query, args.top_k)


if __name__ == "__main__":
    main()

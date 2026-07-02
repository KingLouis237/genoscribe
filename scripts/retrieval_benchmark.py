import argparse
import csv
import json
import pathlib
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from rich.console import Console
from rich.table import Table

from genoscribe.config import OUTPUT_DIR, QUERY_CACHE_FILE, TOP_K_DEFAULT
from genoscribe.indexing.dense_index import DenseRetriever
from genoscribe.indexing.reranker import DenseReranker
from genoscribe.indexing.sparse_index import bm25_score, tokenize
from genoscribe.ingestion.metric_extractor import extract_metrics
from genoscribe.ingestion.table_figure_extractor import strip_figure_noise
from genoscribe.reasoning.query_rewriter import QueryRewriter
from genoscribe.retrieval_hybrid import FilterDecision, hybrid_collect
from genoscribe.search.backends import SearchBackendRegistry, SearchRequest
from genoscribe.storage.provenance_store import (
    load_library,
    load_library_stats,
    rebuild_library_stats,
)

console = Console()

BENCHMARK_QUERIES: List[Tuple[str, str, str]] = [
    ("paper", "PLLR pathogenicity DYNA", "true"),
    ("paper", "foundation model pathogenicity benchmarks", "true"),
    ("assembly", "BUSCO completeness SHINE", "true"),
    ("variant", "ClinVar ARM VUS comparison", "true"),
    ("variant", "predicting disease-causing variant combinations", "true"),
    ("assembly", "ribosome profiling bias", "stress"),
]


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def chunk_type_label(passage) -> str:
    if getattr(passage, "chunk_type", None):
        return passage.chunk_type
    if passage.is_table_or_figure:
        return "table"
    return "body"


def shorten(text: str, limit: int = 80) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def display_safe(text: object) -> str:
    raw = str(text)
    # Some imported PDFs contain Unicode glyphs that fail on legacy Windows cp1252 consoles.
    return raw.encode("cp1252", errors="replace").decode("cp1252")


def compute_bm25_score(passage, query_terms, stats, doc_map) -> float | None:
    doc = doc_map.get(passage.doc_id)
    if not doc:
        return None
    idx = passage.chunk_id
    if idx >= len(doc.term_counts) or idx >= len(doc.doc_lengths):
        return None
    term_counts = doc.term_counts[idx]
    doc_length = doc.doc_lengths[idx]
    return bm25_score(
        query_terms=query_terms,
        doc_terms=term_counts,
        doc_length=doc_length,
        avg_doc_length=stats.avg_doc_length,
        idf_weights=stats.idf_weights,
    )


def serialize_decision(decision: FilterDecision) -> Dict[str, object]:
    passage = decision.passage
    return {
        "doc": pathlib.Path(passage.source_path).name,
        "chunk_id": passage.chunk_id,
        "chunk_type": decision.chunk_type,
        "doc_type": decision.doc_type,
        "kept": decision.kept,
        "final_rank": decision.final_rank,
        "fused_score": decision.fused_score,
        "mode_boost": decision.mode_boost,
        "noise_penalty": decision.noise_penalty,
        "query_overlap": decision.query_overlap,
        "informative_overlap": decision.informative_overlap,
        "query_weight": decision.query_weight,
        "duplicate_of": decision.duplicate_of,
        "figure_quota_hit": decision.figure_quota_hit,
        "reason": decision.reason,
    }


def format_row(doc: str, chunk_id: int, chunk_type: str, score: float | None, snippet: str, reason: str | None) -> str:
    score_txt = f"{score:.3f}" if isinstance(score, float) else "n/a"
    parts = [
        f"{display_safe(doc)} · chunk {chunk_id} ({chunk_type})",
        f"score={score_txt}",
        display_safe(snippet) if snippet else "[no summary]",
    ]
    if reason:
        parts.append(display_safe(reason))
    return " | ".join(parts)


def build_report_rows(passages, scores: Dict[str, float | None], reasons: Dict[str, str]) -> List[Dict[str, object]]:
    rows = []
    for passage in passages:
        key = f"{passage.doc_id}:{passage.chunk_id}"
        rows.append(
            {
                "doc": pathlib.Path(passage.source_path).name,
                "chunk_id": passage.chunk_id,
                "chunk_type": chunk_type_label(passage),
                "doc_type": getattr(passage, "doc_type", "paper") or "paper",
                "score": scores.get(key),
                "snippet": shorten(passage.summary or passage.text or ""),
                "reason": reasons.get(key),
            }
        )
    return rows


def run_query_report(
    *,
    mode: str,
    query: str,
    kind: str,
    registry: SearchBackendRegistry,
    library,
    doc_map,
    stats,
    retriever: DenseRetriever,
    reranker: DenseReranker,
    top_k: int,
    cache_state: str | None = None,
) -> Dict[str, object]:
    rewriter = QueryRewriter()
    rewritten = rewriter.rewrite(query, mode)
    query_terms = tokenize(rewritten)
    bm25_backend = registry.get("bm25")
    bm25_hits = bm25_backend.search(
        library=library,
        stats=stats,
        request=SearchRequest(query=rewritten, top_k=top_k),
    )
    bm25_scores: Dict[str, float | None] = {}
    for passage in bm25_hits:
        key = f"{passage.doc_id}:{passage.chunk_id}"
        bm25_scores[key] = compute_bm25_score(passage, query_terms, stats, doc_map)
    bm25_rows = build_report_rows(bm25_hits, bm25_scores, {})

    reranked_pairs = reranker.rerank(bm25_hits, rewritten, top_k=top_k)
    rerank_scores = {f"{p.doc_id}:{p.chunk_id}": score for p, score in reranked_pairs}
    bm25_rerank_rows = build_report_rows([p for p, _ in reranked_pairs], rerank_scores, {})

    filtered, timings, stage_hits, decisions = hybrid_collect(
        library=library,
        stats=stats,
        query=rewritten,
        search_method="bm25",
        search_registry=registry,
        dense_retriever=retriever,
        reranker=reranker,
        mode=mode,
        base_passages=None,
        top_k=top_k,
        return_decisions=True,
    )
    decision_map = {f"{d.passage.doc_id}:{d.passage.chunk_id}": d for d in decisions}
    reason_map = {key: dec.reason for key, dec in decision_map.items() if dec.kept}
    score_map = {key: decision_map[key].fused_score for key in reason_map}
    hybrid_rows = build_report_rows(filtered, score_map, reason_map)

    return {
        "mode": mode,
        "kind": kind,
        "query": query,
        "rewritten_query": rewritten,
        "cache_state": cache_state,
        "bm25_raw": bm25_rows,
        "bm25_rerank": bm25_rerank_rows,
        "hybrid_final": hybrid_rows,
        "timings": timings,
        "stage_hits": {name: [f"{pathlib.Path(p.source_path).name}:{p.chunk_id}" for p in hits] for name, hits in stage_hits.items()},
        "filter_decisions": [serialize_decision(d) for d in decisions],
    }


def render_retrieval_table(entries: List[Dict[str, object]]) -> None:
    table = Table(show_lines=True, title="Retrieval benchmark: BM25 vs Hybrid")
    table.add_column("Mode")
    table.add_column("Kind")
    table.add_column("Query", overflow="fold")
    table.add_column("BM25 raw", overflow="fold")
    table.add_column("BM25 + rerank", overflow="fold")
    table.add_column("Hybrid final", overflow="fold")
    table.add_column("Timings (ms)", overflow="fold")
    for entry in entries:
        bm25_text = "\n".join(
            format_row(r["doc"], r["chunk_id"], r["chunk_type"], r["score"], r["snippet"], None) for r in entry["bm25_raw"]
        ) or "No hits"
        rerank_text = "\n".join(
            format_row(r["doc"], r["chunk_id"], r["chunk_type"], r["score"], r["snippet"], None) for r in entry["bm25_rerank"]
        ) or "No hits"
        hybrid_text = "\n".join(
            format_row(r["doc"], r["chunk_id"], r["chunk_type"], r["score"], r["snippet"], r["reason"]) for r in entry["hybrid_final"]
        ) or "No hits"
        timings = entry["timings"]
        timing_line = " | ".join(
            f"{key.replace('_ms','')}: {timings[key]:.1f}"
            for key in [
                "sparse_primary_ms",
                "sparse_fallback_ms",
                "dense_embed_ms",
                "dense_search_ms",
                "dense_total_ms",
                "fusion_ms",
                "rerank_ms",
                "quality_filter_ms",
            ]
            if key in timings
        )
        extras = [k for k in timings.keys() if not k.endswith("_ms")]
        if extras:
            more = " | ".join(f"{k}: {timings[k]}" for k in sorted(extras))
            timing_line = f"{timing_line} | {more}" if timing_line else more
        table.add_row(entry["mode"], entry["kind"], entry["query"], bm25_text, rerank_text, hybrid_text, timing_line or "n/a")
    console.print(table)


def write_report(entries: List[Dict[str, object]], top_k: int) -> pathlib.Path:
    report_dir = OUTPUT_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"retrieval_report_{now_stamp()}.json"
    payload = {
        "top_k": top_k,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "queries": entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def render_metric_table(library, export: bool) -> None:
    console.print("\n[bold]DYNA Fig.2 metrics (structured):[/bold]")
    target = None
    for doc in library:
        if "DYNA" not in pathlib.Path(doc.source_path).name:
            continue
        for passage in doc.passages:
            if "p = 7.085e-22" in (passage.raw_text or passage.text or ""):
                target = passage
                break
        if target:
            break
    if not target:
        console.print("[yellow]No DYNA figure chunk found.[/yellow]")
        return
    raw = (target.raw_text or target.text or "")
    cleaned, _ = strip_figure_noise(raw, True)
    metrics = extract_metrics(cleaned, page=target.page)
    if not metrics:
        console.print("[yellow]No metrics extracted.[/yellow]")
        return
    headers = ["Metric", "Value", "Model", "Task", "Dataset", "Panel", "Page", "Chunk", "Source"]
    table = Table(show_lines=True)
    for header in headers:
        table.add_column(header)
    rows_out = []
    for metric in metrics:
        row = [
            metric.get("label") or "Unknown",
            metric.get("value") or "Unknown",
            metric.get("model") or "Unknown",
            metric.get("task") or "Unknown",
            metric.get("dataset") or "Unknown",
            metric.get("panel") or "Unknown",
            str(metric.get("page") or "Unknown"),
            str(target.chunk_id),
            pathlib.Path(target.source_path).name,
        ]
        rows_out.append(row)
        table.add_row(*row)
    console.print(table)
    if export:
        metrics_dir = OUTPUT_DIR / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        csv_path = metrics_dir / f"dyna_metrics_{now_stamp()}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            writer.writerows(rows_out)
        console.print(f"[green]Saved DYNA metric table to[/green] {csv_path}")


def build_doc_map(library) -> Dict[str, object]:
    return {doc.doc_id: doc for doc in library}


def summarize_latency(entries: List[Dict[str, object]]) -> None:
    table = Table(show_lines=True, title="Latency comparison (cold vs warm)")
    table.add_column("Cache")
    table.add_column("Mode")
    table.add_column("Query")
    table.add_column("dense_embed_ms")
    table.add_column("dense_search_ms")
    table.add_column("rerank_ms")
    table.add_column("filter_ms")
    table.add_column("total_ms")
    table.add_column("dense_cache_hit")
    for entry in entries:
        timings = entry["timings"]
        table.add_row(
            entry.get("cache_state", "?"),
            entry["mode"],
            entry["query"],
            f"{timings.get('dense_embed_ms', 0.0):.1f}",
            f"{timings.get('dense_search_ms', 0.0):.1f}",
            f"{timings.get('rerank_ms', 0.0):.1f}",
            f"{timings.get('quality_filter_ms', 0.0):.1f}",
            f"{timings.get('total_ms', 0.0):.1f}",
            str(timings.get("dense_cache_hit", 0.0)),
        )
    console.print(table)


def run_latency_benchmark(library, stats, doc_map, top_k: int) -> pathlib.Path:
    latency_dir = OUTPUT_DIR / "latency"
    latency_dir.mkdir(parents=True, exist_ok=True)
    registry = SearchBackendRegistry()
    if QUERY_CACHE_FILE.exists():
        QUERY_CACHE_FILE.unlink()
    retriever = DenseRetriever()
    retriever.index(library)
    reranker = DenseReranker(retriever)
    cold_entries = [
        run_query_report(
            mode=mode,
            query=query,
            kind=kind,
            registry=registry,
            library=library,
            doc_map=doc_map,
            stats=stats,
            retriever=retriever,
            reranker=reranker,
            top_k=top_k,
            cache_state="cold",
        )
        for mode, query, kind in BENCHMARK_QUERIES
    ]
    warm_entries = [
        run_query_report(
            mode=mode,
            query=query,
            kind=kind,
            registry=registry,
            library=library,
            doc_map=doc_map,
            stats=stats,
            retriever=retriever,
            reranker=reranker,
            top_k=top_k,
            cache_state="warm",
        )
        for mode, query, kind in BENCHMARK_QUERIES
    ]
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "top_k": top_k,
        "runs": [
            {"cache_state": "cold", "queries": cold_entries},
            {"cache_state": "warm", "queries": warm_entries},
        ],
    }
    path = latency_dir / f"latency_{now_stamp()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_rows = []
    for run in payload["runs"]:
        for entry in run["queries"]:
            total_ms = sum(
                entry["timings"].get(key, 0.0)
                for key in (
                    "sparse_primary_ms",
                    "sparse_fallback_ms",
                    "dense_total_ms",
                    "fusion_ms",
                    "rerank_ms",
                    "quality_filter_ms",
                )
            )
            summary_rows.append(
                {
                    "cache_state": run["cache_state"],
                    "mode": entry["mode"],
                    "query": entry["query"],
                    "timings": {
                        **entry["timings"],
                        "total_ms": total_ms,
                    },
                }
            )
    summarize_latency(summary_rows)
    console.print(f"[green]Saved latency report to[/green] {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GenoScribe retrieval benchmark.")
    parser.add_argument("--top-k", type=int, default=TOP_K_DEFAULT)
    parser.add_argument("--export", action="store_true", help="Write retrieval and metric reports to outputs/")
    parser.add_argument("--latency-run", action="store_true", help="Run cold vs warm latency benchmark")
    args = parser.parse_args()

    library = load_library()
    if not library:
        console.print("[red]Library is empty. Ingest documents first.[/red]")
        return

    stats = load_library_stats()
    if not stats or stats.total_docs != len(library):
        stats = rebuild_library_stats(library)

    retriever = DenseRetriever()
    retriever.index(library)
    reranker = DenseReranker(retriever)
    registry = SearchBackendRegistry()
    doc_map = build_doc_map(library)

    entries = [
        run_query_report(
            mode=mode,
            query=query,
            kind=kind,
            registry=registry,
            library=library,
            doc_map=doc_map,
            stats=stats,
            retriever=retriever,
            reranker=reranker,
            top_k=args.top_k,
        )
        for mode, query, kind in BENCHMARK_QUERIES
    ]
    render_retrieval_table(entries)
    if args.export:
        report_path = write_report(entries, args.top_k)
        console.print(f"[green]Saved retrieval report to[/green] {report_path}")
    render_metric_table(library, export=args.export)

    if args.latency_run:
        run_latency_benchmark(library, stats, doc_map, args.top_k)


if __name__ == "__main__":
    main()

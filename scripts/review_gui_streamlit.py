from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import pandas as pd
import streamlit as st

from genoscribe.app.review_service import EvidenceReviewService
from genoscribe.config import OUTPUT_DIR
from genoscribe.eval.report_viewer import (
    compare_reports,
    failed_rows,
    failure_breakdown,
    get_rows,
    row_key,
    summarize_report,
)
from genoscribe.schemas.document import Passage
from genoscribe.schemas.review import ReviewQueryResult

MODES = ["paper", "assembly", "variant"]


def _get_service() -> EvidenceReviewService:
    if "review_service" not in st.session_state:
        st.session_state["review_service"] = EvidenceReviewService()
    return st.session_state["review_service"]


def _candidate_dataframe(result: ReviewQueryResult) -> pd.DataFrame:
    rows = []
    for idx, candidate in enumerate(result.candidates, start=1):
        rows.append(
            {
                "rank": idx,
                "doc": candidate.doc_name,
                "chunk_id": candidate.chunk_id,
                "chunk_type": candidate.chunk_type,
                "doc_type": candidate.doc_type,
                "score": candidate.fused_score,
                "snippet": (candidate.summary or "").replace("\n", " ")[:200],
            }
        )
    return pd.DataFrame(rows)


def _metrics_dataframe(result: ReviewQueryResult) -> pd.DataFrame:
    rows = []
    for metric in result.metrics:
        rows.append(
            {
                "metric": metric.label,
                "value": metric.value,
                "model": metric.model,
                "dataset": metric.dataset,
                "task": metric.task,
                "chunk": f"{metric.doc_id}:{metric.chunk_id}",
                "confidence": metric.confidence,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["metric", "value", "model", "dataset", "task", "chunk", "confidence"])
    return pd.DataFrame(rows)


def _selected_key(result: ReviewQueryResult) -> Optional[str]:
    keys = [f"{c.doc_id}:{c.chunk_id}" for c in result.candidates]
    if not keys:
        return None
    current = st.session_state.get("selected_candidate")
    if current in keys:
        default_key = current
    else:
        default_key = keys[0]
    display = {key: label for key, label in zip(keys, _display_labels(result))}
    selected = st.selectbox("Select candidate", options=list(display.keys()), format_func=lambda k: display[k], index=keys.index(default_key))
    st.session_state["selected_candidate"] = selected
    return selected


def _display_labels(result: ReviewQueryResult) -> List[str]:
    labels: List[str] = []
    for idx, candidate in enumerate(result.candidates, start=1):
        labels.append(f"{idx}. {candidate.doc_name} · chunk {candidate.chunk_id} ({candidate.chunk_type})")
    return labels


def _render_passage(passage: Passage | None, key: str | None, result: ReviewQueryResult) -> None:
    if passage is None:
        st.info("Select a candidate to view passage details.")
        return
    st.subheader("Source passage")
    st.write(f"**Chunk:** {passage.doc_id}:{passage.chunk_id} · page {passage.page or 'n/a'}")
    if passage.summary:
        st.write(f"**Summary:** {passage.summary}")
    st.write("**Full text:**")
    st.code(passage.text or "(no full text)", language="text")

    meta = result.metadata.get(key or "")
    trace = result.filter_traces.get(key or "")
    with st.expander("Chunk metadata", expanded=True):
        if meta:
            st.json(
                {
                    "chunk_type": meta.chunk_type,
                    "doc_type": meta.doc_type,
                    "noise_level": meta.noise_level,
                    "has_metrics": meta.has_metrics,
                    "is_table_or_figure": meta.is_table_or_figure,
                }
            )
        else:
            st.write("No metadata available.")
    with st.expander("Filter decision trace", expanded=True):
        if trace:
            st.json(
                {
                    "fused_score": trace.fused_score,
                    "mode_boost": trace.mode_boost,
                    "noise_penalty": trace.noise_penalty,
                    "query_overlap": trace.query_overlap,
                    "informative_overlap": trace.informative_overlap,
                    "query_weight": trace.query_weight,
                    "kept": trace.kept,
                    "reason": trace.reason,
                    "duplicate_of": trace.duplicate_of,
                    "figure_quota_hit": trace.figure_quota_hit,
                }
            )
        else:
            st.write("No filter trace recorded.")


def _render_bundle(result: ReviewQueryResult) -> None:
    preview = result.bundle_preview
    st.subheader("Evidence bundle")
    cols = st.columns(3)
    cols[0].metric("Bundle type", preview.bundle_type)
    cols[1].metric("Coverage notes", len(preview.coverage_notes))
    cols[2].metric("Contradictions", len(preview.contradictions))
    st.write("**Coverage counts:**")
    st.json(preview.coverage_counts)
    if preview.coverage_notes:
        st.write("**Notes:**")
        for note in preview.coverage_notes:
            st.write(f"- {note}")
    if preview.unresolved_requests:
        st.warning(
            "Unresolved / missing coverage: "
            + ", ".join(preview.unresolved_requests),
        )
    if preview.contradictions:
        with st.expander("Contradictions"):
            for conflict in preview.contradictions:
                st.write(f"- {conflict}")


def _render_structured(result: ReviewQueryResult) -> None:
    structured = result.structured_answer
    st.subheader("Structured answer & audit")
    st.write(f"**Mode:** {structured.mode}")
    st.write(f"**Audit status:** {structured.audit_status}")
    if structured.verifier_notes:
        st.write("**Verifier notes:**")
        for note in structured.verifier_notes:
            st.write(f"- {note}")
    st.write("**Rendered output:**")
    st.code(structured.rendered_text or "(no structured output)", language="markdown")


def _render_diagnostics(result: ReviewQueryResult) -> None:
    diag = result.diagnostics
    st.subheader("Diagnostics")
    st.write("**Timing (ms):**")
    st.json(diag.timings_ms)
    st.write("**Cache stats:**")
    st.json(diag.cache_stats)
    st.write("**Stage hits:**")
    st.json(diag.stage_hits)
    if diag.benchmark_artifacts:
        with st.expander("Other artifacts", expanded=False):
            artifact_rows = []
            for raw_path in diag.benchmark_artifacts:
                path = Path(raw_path)
                artifact_rows.append(
                    {
                        "filename": path.name,
                        "type": _artifact_type(path.name),
                        "timestamp": _extract_timestamp(path.name) or "",
                    }
                )
            st.dataframe(pd.DataFrame(artifact_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No benchmark artifacts detected. Run `uv run python scripts/retrieval_benchmark.py --export` to generate them.")


def _reports_dir() -> Path:
    return OUTPUT_DIR / "reports"


def _report_files() -> List[Path]:
    report_dir = _reports_dir()
    if not report_dir.exists():
        return []
    paths = list(report_dir.glob("paper_validation_*.json")) + list(report_dir.glob("paper_probe_report_*.json"))
    return sorted([path for path in paths if path.is_file()], reverse=True)


def _artifact_type(filename: str) -> str:
    if filename.startswith("paper_validation_"):
        return "validation_report"
    if filename.startswith("paper_probe_report_"):
        return "probe_report"
    if filename.startswith("paper_probe_summary_"):
        return "probe_summary_csv"
    if filename.startswith("corpus_inventory_"):
        return "corpus_inventory"
    if filename.startswith("corpus_probe_integrity_"):
        return "corpus_integrity"
    if filename.startswith("retrieval_report_"):
        return "retrieval_report"
    if filename.startswith("structured_"):
        return "structured_output"
    if filename.endswith(".csv"):
        return "csv_artifact"
    return "other"


def _extract_timestamp(filename: str) -> str | None:
    match = re.search(r"(\d{8}_\d{6})", filename)
    if not match:
        return None
    stamp = match.group(1)
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"


def _load_report(path: Path) -> Mapping[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _breakdown_df(values: Dict[str, int], key_name: str) -> pd.DataFrame:
    if not values:
        return pd.DataFrame(columns=[key_name, "count"])
    rows = [{key_name: key, "count": count} for key, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))]
    return pd.DataFrame(rows)


def _render_report_summary(payload: Mapping[str, object], report_name: str) -> None:
    summary = summarize_report(payload)
    st.write(f"**Report:** `{report_name}`")
    cols = st.columns(5)
    cols[0].metric("Total tasks", summary.total)
    pass_rate_text = f"{summary.pass_rate * 100:.1f}%" if summary.pass_rate is not None else "n/a"
    cols[1].metric("Pass rate", pass_rate_text)
    cols[2].metric(
        "Target inferred",
        f"{summary.target_doc_inferred_count}/{summary.total}",
        f"{summary.target_doc_inferred_rate * 100:.1f}%",
    )
    cols[3].metric(
        "Final overlap",
        f"{summary.final_doc_overlap_count}/{summary.total}",
        f"{summary.final_doc_overlap_rate * 100:.1f}%",
    )
    cols[4].metric("Report type", summary.kind)
    st.write("**Audit status counts**")
    st.dataframe(
        _breakdown_df(summary.audit_status_counts, "audit_status"),
        use_container_width=True,
        hide_index=True,
    )


def _render_failure_breakdowns(payload: Mapping[str, object]) -> None:
    breakdown = failure_breakdown(payload)
    st.write("**Failure breakdown**")
    col1, col2 = st.columns(2)
    with col1:
        st.write("By document")
        st.dataframe(_breakdown_df(breakdown["by_document"], "document"), use_container_width=True, hide_index=True)
        st.write("By failed check")
        st.dataframe(_breakdown_df(breakdown["by_failed_check"], "failed_check"), use_container_width=True, hide_index=True)
    with col2:
        st.write("By query/task type")
        st.dataframe(_breakdown_df(breakdown["by_task_type"], "task_type"), use_container_width=True, hide_index=True)
        st.write("By audit status")
        st.dataframe(_breakdown_df(breakdown["by_audit_status"], "audit_status"), use_container_width=True, hide_index=True)


def _render_failed_row_drilldown(payload: Mapping[str, object]) -> None:
    kind, rows = failed_rows(payload)
    if not rows:
        st.success("No failed rows in this report.")
        return
    options = {row_key(kind, row): row for row in rows}
    selected_key = st.selectbox("Select failed row", options=list(options.keys()))
    row = options[selected_key]
    st.write("**Failure row details**")
    expected_doc_ids = row.get("expected_doc_ids", [])
    target_doc_ids = row.get("target_doc_ids", [])
    final_doc_ids = row.get("final_doc_ids", [])
    st.json(
        {
            "document": row.get("slug", row.get("paper_slug")),
            "task_type": row.get("task_type"),
            "query": row.get("query"),
            "expected_target_doc_ids": expected_doc_ids,
            "target_doc_ids": target_doc_ids,
            "target_scope_source": row.get("target_scope_source", "n/a"),
            "final_doc_ids": final_doc_ids,
            "audit_status": row.get("audit_status"),
            "metric_count": row.get("metric_count", 0),
        }
    )
    rendered = ""
    if kind == "probe":
        structured = row.get("structured_answer")
        if isinstance(structured, Mapping):
            rendered = str(structured.get("rendered_text") or "")
    else:
        structured_result = row.get("structured_result")
        if isinstance(structured_result, Mapping):
            structured_answer = structured_result.get("structured_answer")
            if isinstance(structured_answer, Mapping):
                rendered = str(structured_answer.get("rendered_text") or "")
    if rendered:
        st.write("**Rendered output**")
        st.code(rendered, language="markdown")
    else:
        st.info("No rendered output available for this row.")


def _render_report_compare(paths: List[Path]) -> None:
    st.write("**Compare two reports (optional)**")
    if len(paths) < 2:
        st.info("Need at least two report files to compare.")
        return
    path_map = {path.name: path for path in paths}
    col1, col2 = st.columns(2)
    with col1:
        base_name = st.selectbox("Baseline report", options=list(path_map.keys()), key="compare_base")
    with col2:
        cand_name = st.selectbox("Candidate report", options=list(path_map.keys()), index=1, key="compare_candidate")
    if base_name == cand_name:
        st.info("Select two different reports to compare.")
        return
    try:
        comparison = compare_reports(_load_report(path_map[base_name]), _load_report(path_map[cand_name]))
    except Exception as exc:  # pragma: no cover - UI safeguard
        st.warning(f"Could not compare reports: {exc}")
        return
    cols = st.columns(4)
    cols[0].metric("Common rows", comparison["common_rows"])
    cols[1].metric("Fixed", len(comparison["fixed"]))
    cols[2].metric("Regressed", len(comparison["regressed"]))
    cols[3].metric("Unchanged fail", len(comparison["unchanged_fail"]))
    with st.expander("Fixed row keys"):
        st.write(comparison["fixed"] or ["(none)"])
    with st.expander("Regressed row keys"):
        st.write(comparison["regressed"] or ["(none)"])


def _render_report_viewer_tab() -> None:
    st.subheader("Validation / Probe report viewer")
    st.caption(
        "Use this tab to inspect paper validation and paper probe JSON reports. "
        "It intentionally focuses on report summaries and failure drill-downs."
    )
    reports = _report_files()
    if not reports:
        st.info("No paper_validation_*.json or paper_probe_report_*.json files found in outputs/reports.")
        return
    latest_validation = next((path for path in reports if path.name.startswith("paper_validation_")), None)
    latest_probe = next((path for path in reports if path.name.startswith("paper_probe_report_")), None)
    landing_rows = []
    if latest_validation:
        landing_rows.append(
            {
                "filename": latest_validation.name,
                "type": "validation_report",
                "timestamp": _extract_timestamp(latest_validation.name) or "",
            }
        )
    if latest_probe:
        landing_rows.append(
            {
                "filename": latest_probe.name,
                "type": "probe_report",
                "timestamp": _extract_timestamp(latest_probe.name) or "",
            }
        )
    if landing_rows:
        st.write("**Latest reports**")
        st.dataframe(pd.DataFrame(landing_rows), use_container_width=True, hide_index=True)

    report_map = {path.name: path for path in reports}
    selected_name = st.selectbox("Select report", options=list(report_map.keys()))
    selected_path = report_map[selected_name]
    try:
        payload = _load_report(selected_path)
    except Exception as exc:  # pragma: no cover - UI safeguard
        st.error(f"Failed to load report: {exc}")
        return
    _render_report_summary(payload, selected_name)
    _render_failure_breakdowns(payload)
    _render_failed_row_drilldown(payload)
    _render_report_compare(reports)
    with st.expander("Other artifacts", expanded=False):
        report_dir = _reports_dir()
        others = sorted(
            [path for path in report_dir.glob("*") if path.is_file() and path.name not in report_map],
            reverse=True,
        )
        if not others:
            st.info("No additional artifacts in outputs/reports.")
        else:
            rows = [
                {
                    "filename": path.name,
                    "type": _artifact_type(path.name),
                    "timestamp": _extract_timestamp(path.name) or "",
                }
                for path in others
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_metrics_section(result: ReviewQueryResult) -> None:
    st.subheader("Extracted metrics")
    df = _metrics_dataframe(result)
    if df.empty:
        st.info("No metrics extracted for these passages.")
        return
    st.dataframe(df, use_container_width=True)


def _render_candidates_section(result: ReviewQueryResult) -> Optional[str]:
    st.subheader("Ranked retrieval candidates")
    df = _candidate_dataframe(result)
    if df.empty:
        st.warning("No candidates returned for this query.")
        return None
    st.dataframe(df, use_container_width=True)
    return _selected_key(result)


def _run_query(service: EvidenceReviewService, query: str, mode: str) -> Optional[ReviewQueryResult]:
    if not query:
        st.warning("Enter a query to run retrieval.")
        return None
    try:
        result = service.run_query(query=query, mode=mode)
    except Exception as exc:  # pragma: no cover - UI safeguard
        st.error(f"Failed to run evidence review: {exc}")
        return None
    st.session_state["last_result"] = result
    st.session_state["query_text"] = query
    st.session_state["mode_value"] = mode
    st.session_state["selected_candidate"] = None
    return result


def render_app() -> None:
    st.set_page_config(page_title="GenoScribe Evidence Review", layout="wide")
    st.title("GenoScribe Evidence Review")
    evidence_tab, reports_tab = st.tabs(["Evidence review", "Report viewer"])

    with evidence_tab:
        service = _get_service()
        if not service.library:
            st.info(
                "No indexed documents found. Build the synthetic demo corpus or ingest your own papers before running evidence review."
            )
            st.code(
                "uv run python scripts/demo_build_sample_corpus.py\n"
                "uv run streamlit run scripts/review_gui_streamlit.py",
                language="bash",
            )
        else:
            query_default = st.session_state.get("query_text", "")
            mode_default = st.session_state.get("mode_value", "paper")
            query = st.text_input("Query", value=query_default, key="query_input")
            mode = st.selectbox("Mode", options=MODES, index=MODES.index(mode_default), key="mode_select")
            run = st.button("Run evidence review", type="primary")

            result: Optional[ReviewQueryResult] = st.session_state.get("last_result")
            if run:
                result = _run_query(service, query.strip(), mode)

            if result is None:
                st.info("Run a query to inspect retrieval evidence.")
            else:
                selected_key = _render_candidates_section(result)
                if selected_key:
                    passage = result.passage_map.get(selected_key)
                else:
                    passage = None
                _render_passage(passage, selected_key, result)
                _render_metrics_section(result)
                _render_bundle(result)
                _render_structured(result)
                _render_diagnostics(result)

    with reports_tab:
        _render_report_viewer_tab()


def main() -> None:
    render_app()


if __name__ == "__main__":
    main()

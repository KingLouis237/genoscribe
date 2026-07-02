from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from genoscribe.schemas.review import (
    CandidateView,
    DiagnosticsReport,
    EvidenceBundlePreview,
    ReviewQueryResult,
    StructuredAnswerView,
)

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "paper_probe_runner.py"
_MODULE_SPEC = importlib.util.spec_from_file_location("paper_probe_runner", _MODULE_PATH)
assert _MODULE_SPEC is not None and _MODULE_SPEC.loader is not None
probe_runner = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(probe_runner)


class _FakeReviewService:
    last_instance: "_FakeReviewService | None" = None

    def __init__(self, top_k: int = 4) -> None:
        self.top_k = top_k
        self.library = [SimpleNamespace(doc_id="doc1", source_path="doc1.pdf", doc_type="paper")]
        self.calls: list[tuple[str, list[str] | None]] = []
        type(self).last_instance = self

    def run_query(
        self,
        *,
        query: str,
        mode: str = "paper",
        top_k: int | None = None,
        target_doc_ids_override=None,
    ) -> ReviewQueryResult:
        override = [str(doc_id) for doc_id in target_doc_ids_override] if target_doc_ids_override else None
        self.calls.append((query, override))
        target_doc_ids = list(override) if override else ["doc1"]
        candidate = CandidateView(
            doc_id="doc1",
            source_path="doc1.pdf",
            chunk_id=0,
            page=1,
            chunk_type="body",
            doc_type="paper",
            summary="stub",
            fused_score=0.9,
            kept=True,
            final_rank=1,
        )
        structured = StructuredAnswerView(
            mode=mode,
            structured=None,
            rendered_text="stub",
            audit_status="supported",
            verifier_notes=[],
        )
        bundle = EvidenceBundlePreview(bundle_type=mode, coverage_notes=[], coverage_counts={})
        diagnostics = DiagnosticsReport(timings_ms={}, cache_stats={}, stage_hits={})
        return ReviewQueryResult(
            mode=mode,
            query=query,
            rewritten_query=query,
            candidates=[candidate],
            passage_map={},
            metadata={},
            filter_traces={},
            metrics=[],
            bundle_preview=bundle,
            structured_answer=structured,
            diagnostics=diagnostics,
            target_doc_ids=target_doc_ids,
        )


def test_probe_runner_uses_override_only_for_deictic_queries(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    probes_path = tmp_path / "probes.json"
    manifest_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "slug": "doc_slug",
                        "title": "Doc Title",
                        "filename": "doc1.pdf",
                        "buckets": ["generalization"],
                        "modes": ["paper"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    probes_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "slug": "doc_slug",
                        "queries": [
                            {
                                "id": "explicit",
                                "task_type": "scoped_claim_query",
                                "query": "In the Doc Title paper, summarize findings.",
                            },
                            {
                                "id": "deictic",
                                "task_type": "unsupported_topic_query",
                                "query": "In this paper, what off-target rates are reported?",
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(probe_runner, "EvidenceReviewService", _FakeReviewService)
    monkeypatch.setattr(probe_runner, "OUTPUT_DIR", tmp_path)

    json_path, _ = probe_runner.run_probes(manifest_path=Path(manifest_path), probes_path=Path(probes_path), top_k=4)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows = {row["query_id"]: row for row in payload["rows"]}

    assert rows["explicit"]["target_scope_source"] == "inferred"
    assert rows["deictic"]["target_scope_source"] == "context_override"

    service = _FakeReviewService.last_instance
    assert service is not None
    call_map = {query: override for query, override in service.calls}
    assert call_map["In the Doc Title paper, summarize findings."] is None
    assert call_map["In this paper, what off-target rates are reported?"] == ["doc1"]

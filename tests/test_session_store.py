import json
from pathlib import Path

import pytest

from genoscribe.session_store import SessionStore


@pytest.fixture
def sample_payload() -> dict:
    return {
        "conversation": [{"role": "user", "content": "hello"}],
        "working_notes": ["note"],
        "mode": "paper",
        "template": "strict_evidence",
        "search_method": "bm25",
        "pending_citations": [],
        "last_evidence_sources": [],
    }


def test_save_load_snapshot(tmp_path, sample_payload):
    store = SessionStore(root=tmp_path)
    snapshot = store.save_snapshot("My Session", sample_payload, description="weekly sync")

    assert snapshot.name == "My_Session"
    assert snapshot.message_count == 1

    assert (tmp_path / "My_Session.json").exists()
    data = json.loads((tmp_path / "My_Session.json").read_text(encoding="utf-8"))
    assert data["description"] == "weekly sync"
    assert data["conversation"][0]["content"] == "hello"
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")

    loaded = store.load_snapshot("My Session")
    assert loaded.payload["working_notes"] == ["note"]
    assert loaded.updated_at >= loaded.created_at


def test_list_snapshots_sorted(tmp_path, sample_payload):
    store = SessionStore(root=tmp_path)
    store.save_snapshot("first", sample_payload)
    store.save_snapshot("second", sample_payload)

    names = [snap.name for snap in store.list_snapshots()]
    assert names[0] == "second"  # most recent first


def test_list_snapshots_has_deterministic_tie_breaker(tmp_path, sample_payload):
    same_time = "2026-07-02T00:00:00.000000Z"
    for name in ("first", "second"):
        data = dict(sample_payload)
        data.update({"name": name, "created_at": same_time, "updated_at": same_time})
        (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    names = [snap.name for snap in SessionStore(root=tmp_path).list_snapshots()]

    assert names == ["second", "first"]


def test_legacy_snapshot_without_updated_at_uses_created_at(tmp_path, sample_payload):
    data = dict(sample_payload)
    data.update({"name": "legacy", "created_at": "2026-07-02T00:00:00.123456Z"})
    (tmp_path / "legacy.json").write_text(json.dumps(data), encoding="utf-8")

    snapshot = SessionStore(root=tmp_path).load_snapshot("legacy")

    assert snapshot.updated_at == snapshot.created_at


def test_delete_snapshot(tmp_path, sample_payload):
    store = SessionStore(root=tmp_path)
    store.save_snapshot("temp", sample_payload)
    store.delete_snapshot("temp")

    with pytest.raises(FileNotFoundError):
        store.load_snapshot("temp")


def test_invalid_snapshot_name(tmp_path, sample_payload):
    store = SessionStore(root=tmp_path)
    with pytest.raises(ValueError):
        store.save_snapshot("!!!", sample_payload)

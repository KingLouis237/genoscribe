from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from genoscribe.config import OUTPUT_DIR


@dataclass
class SessionSnapshot:
    """Placeholder for richer session metadata."""

    name: str
    path: Path
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0
    payload: Optional[Dict[str, Any]] = None
    overwritten: bool = False


class SessionStore:
    """Manage persistence of named session snapshots on disk."""

    root: Path

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or (OUTPUT_DIR / "snapshots")
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_snapshots(self) -> List[SessionSnapshot]:
        snapshots: List[SessionSnapshot] = []
        for fp in self.root.glob("*.json"):
            try:
                obj = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue

            fallback_ts = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
            created_at = self._parse_timestamp(obj.get("created_at"), fallback=fallback_ts)
            updated_at = self._parse_timestamp(obj.get("updated_at"), fallback=created_at)
            snapshot = SessionSnapshot(
                name=obj.get("name", fp.stem),
                path=fp,
                description=obj.get("description", ""),
                created_at=created_at,
                updated_at=updated_at,
                message_count=len(obj.get("conversation", [])),
            )
            snapshots.append(snapshot)

        snapshots.sort(key=lambda s: (s.updated_at, s.created_at, s.path.stat().st_mtime_ns, s.name), reverse=True)
        return snapshots

    def save_snapshot(self, name: str, payload: Dict[str, Any], description: str = "") -> SessionSnapshot:
        sanitized = self._sanitize_name(name)
        path = self._path_for_name(sanitized)
        is_overwrite = path.exists()
        now = datetime.now(timezone.utc)
        existing_created_at: Optional[datetime] = None
        if is_overwrite:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                fallback_ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                existing_created_at = self._parse_timestamp(existing.get("created_at"), fallback=fallback_ts)
            except Exception:
                existing_created_at = None
        created_at = existing_created_at or now

        data = dict(payload)
        data.update({
            "name": sanitized,
            "description": description,
            "created_at": self._format_timestamp(created_at),
            "updated_at": self._format_timestamp(now),
        })

        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return SessionSnapshot(
            name=sanitized,
            path=path,
            description=description,
            created_at=created_at,
            updated_at=now,
            message_count=len(data.get("conversation", [])),
            payload=data,
            overwritten=is_overwrite,
        )

    def load_snapshot(self, name: str) -> SessionSnapshot:
        sanitized = self._sanitize_name(name)
        path = self._path_for_name(sanitized)
        if not path.exists():
            raise FileNotFoundError(f"Snapshot '{sanitized}' not found.")

        data = json.loads(path.read_text(encoding="utf-8"))
        fallback_ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        created_at = self._parse_timestamp(data.get("created_at"), fallback=fallback_ts)
        updated_at = self._parse_timestamp(data.get("updated_at"), fallback=created_at)

        return SessionSnapshot(
            name=data.get("name", sanitized),
            path=path,
            description=data.get("description", ""),
            created_at=created_at,
            updated_at=updated_at,
            message_count=len(data.get("conversation", [])),
            payload=data,
        )

    def delete_snapshot(self, name: str) -> None:
        sanitized = self._sanitize_name(name)
        path = self._path_for_name(sanitized)
        if not path.exists():
            raise FileNotFoundError(f"Snapshot '{sanitized}' not found.")
        path.unlink()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _path_for_name(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def _sanitize_name(self, name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip())
        cleaned = cleaned.strip("_")
        if not cleaned:
            raise ValueError("Snapshot name must include at least one alphanumeric character.")
        if len(cleaned) > 64:
            cleaned = cleaned[:64]
        return cleaned

    def _parse_timestamp(self, value: Optional[str], *, fallback: Optional[datetime] = None) -> datetime:
        if value:
            try:
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                return datetime.fromisoformat(value)
            except Exception:
                pass
        return fallback or datetime.fromtimestamp(0, tz=timezone.utc)

    def _format_timestamp(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")

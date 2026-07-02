from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class SQLiteStore:
    """Placeholder for structured metadata persistence."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure_schema(self) -> None:  # pragma: no cover - scaffold
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def upsert(self, table: str, record: Dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError("SQLite telemetry store not yet implemented")


__all__ = ["SQLiteStore"]

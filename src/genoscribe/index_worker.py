from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class IndexingJob:
    """Lightweight job descriptor for the future background indexing service."""

    paths: List[Path]
    priority: int = 0


class BackgroundIndexer:
    """
    Scaffold for a background indexing queue.

    Future work will wire this into a thread or async worker that
    processes IndexingJob instances while the user continues chatting.
    """

    def __init__(self) -> None:
        self._queue: List[IndexingJob] = []

    def submit(self, job: IndexingJob) -> None:
        self._queue.append(job)

    def pending_jobs(self) -> List[IndexingJob]:
        return list(self._queue)

    def run_once(self, library_dir: Optional[Path] = None) -> None:
        raise NotImplementedError("Background processing not implemented yet.")

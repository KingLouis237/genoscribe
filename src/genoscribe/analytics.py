from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from genoscribe.config import DATA_DIR


@dataclass
class AnalyticsEvent:
    """Structured event used for future retrieval quality tracking."""

    name: str
    payload: Dict[str, str]
    timestamp: _dt.datetime = field(default_factory=_dt.datetime.utcnow)


class AnalyticsLogger:
    """
    Placeholder analytics sink.

    The final implementation might ship events to disk, a dashboard, or an
    offline evaluator. For now we just define the API surface.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or (DATA_DIR / "analytics")

    def emit(self, event: AnalyticsEvent) -> None:
        raise NotImplementedError("Analytics logging not implemented yet.")

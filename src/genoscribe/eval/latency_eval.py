from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable


@dataclass
class LatencyStats:
    p50: float
    p95: float
    mean: float


def summarize_latencies(latencies_ms: Iterable[float]) -> LatencyStats:
    values = list(latencies_ms)
    if not values:
        return LatencyStats(p50=0.0, p95=0.0, mean=0.0)
    values.sort()
    p50 = statistics.median(values)
    p95 = values[int(0.95 * (len(values) - 1))]
    return LatencyStats(p50=p50, p95=p95, mean=statistics.mean(values))


__all__ = ["LatencyStats", "summarize_latencies"]

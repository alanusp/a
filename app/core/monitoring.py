from __future__ import annotations

import statistics
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional

from app.core.telemetry_sampling import AdaptiveSampler, SamplingDecision


@dataclass
class LatencyTracker:
    """Track inference latency in milliseconds for observability dashboards."""

    window_size: int = 200
    measurements: Deque[float] = field(default_factory=deque)
    sampler: Optional[AdaptiveSampler] = None
    reasons: Counter[str] = field(default_factory=Counter)

    def add(self, value_ms: float, *, is_error: bool = False) -> None:
        decision: SamplingDecision | None = None
        if self.sampler is not None:
            decision = self.sampler.should_sample(value_ms, is_error=is_error)
            if not decision.sampled:
                return
            self.reasons[decision.reason] += 1
        else:
            self.reasons["unsampled"] += 1
        self.measurements.append(value_ms)
        if len(self.measurements) > self.window_size:
            self.measurements.popleft()

    def summary(self) -> Dict[str, float]:
        if not self.measurements:
            return {"p50": 0.0, "p90": 0.0, "p99": 0.0, "avg": 0.0}
        values = sorted(self.measurements)

        def percentile(vals: List[float], percentile: float) -> float:
            if len(vals) == 1:
                return vals[0]
            rank = (len(vals) - 1) * percentile
            lower = int(rank)
            upper = min(lower + 1, len(vals) - 1)
            weight = rank - lower
            return vals[lower] * (1 - weight) + vals[upper] * weight

        payload = {
            "p50": percentile(values, 0.50),
            "p90": percentile(values, 0.90),
            "p99": percentile(values, 0.99),
            "avg": statistics.fmean(values),
        }
        if self.sampler is not None:
            payload.update({f"samples_{reason}": float(count) for reason, count in self.reasons.items()})
            payload.update(self.sampler.summary())
        return payload


class ThroughputTracker:
    """Track throughput in events per second."""

    def __init__(self, window_seconds: float = 5.0) -> None:
        self.window_seconds = window_seconds
        self.events: Deque[float] = deque()

    def mark(self) -> None:
        now = time.monotonic()
        self.events.append(now)
        while self.events and now - self.events[0] > self.window_seconds:
            self.events.popleft()

    def eps(self) -> float:
        if not self.events:
            return 0.0
        window = max(time.monotonic() - self.events[0], 1e-6)
        return len(self.events) / window


def report_metrics(latencies: Iterable[float]) -> Dict[str, float]:
    tracker = LatencyTracker()
    for latency in latencies:
        tracker.add(latency)
    return tracker.summary()

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass(slots=True)
class LatencyHistogram:
    significant_figures: int = 3
    lowest_trackable: int = 1
    highest_trackable: int = 60_000
    _counts: Dict[int, int] = field(default_factory=dict)

    def record(self, value_ms: float) -> None:
        bucket = self._bucket_index(value_ms)
        self._counts[bucket] = self._counts.get(bucket, 0) + 1

    def merge(self, other: "LatencyHistogram") -> "LatencyHistogram":
        for bucket, count in other._counts.items():
            self._counts[bucket] = self._counts.get(bucket, 0) + count
        return self

    def percentile(self, quantile: float) -> float:
        total = sum(self._counts.values())
        if not total:
            return 0.0
        threshold = total * quantile
        running = 0
        for bucket in sorted(self._counts):
            running += self._counts[bucket]
            if running >= threshold:
                return float(bucket)
        return float(self.highest_trackable)

    def to_json(self) -> str:
        return json.dumps(self._counts, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "LatencyHistogram":
        histogram = cls()
        histogram._counts = {int(bucket): int(count) for bucket, count in json.loads(payload).items()}
        return histogram

    def _bucket_index(self, value_ms: float) -> int:
        clamped = min(max(int(value_ms), self.lowest_trackable), self.highest_trackable)
        if clamped == 0:
            return 0
        exponent = max(int(math.log10(clamped)) - (self.significant_figures - 1), 0)
        magnitude = 10 ** exponent
        return (clamped // magnitude) * magnitude


def load_histogram(path: Path) -> LatencyHistogram:
    if not path.exists():
        return LatencyHistogram()
    return LatencyHistogram.from_json(path.read_text())


def compare_histograms(new_histogram: LatencyHistogram, baseline: LatencyHistogram, *, p95_budget: float) -> Dict[str, float]:
    current_p95 = new_histogram.percentile(0.95)
    baseline_p95 = baseline.percentile(0.95)
    regression = current_p95 - baseline_p95
    status = 0.0 if regression <= p95_budget else 1.0
    return {
        "current_p95": current_p95,
        "baseline_p95": baseline_p95,
        "regression_ms": regression,
        "regression_flag": status,
    }

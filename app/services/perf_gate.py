from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable, Sequence

from app.core.config import get_settings


def _load_samples(path: Path) -> list[float]:
    if not path.exists():
        raise FileNotFoundError(f"baseline samples missing at {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "latencies" in payload:
        data = payload["latencies"]
    else:
        data = payload
    return [float(value) for value in data]


def _empirical_cdf(samples: Sequence[float], value: float) -> float:
    if not samples:
        return 0.0
    count = sum(1 for sample in samples if sample <= value)
    return count / len(samples)


def _ks_statistic(baseline: Sequence[float], candidate: Sequence[float]) -> float:
    combined = sorted(set(baseline) | set(candidate))
    if not combined:
        return 0.0
    max_diff = 0.0
    for value in combined:
        diff = abs(_empirical_cdf(candidate, value) - _empirical_cdf(baseline, value))
        max_diff = max(max_diff, diff)
    return max_diff


def _critical_value(n: int, m: int, alpha: float = 0.05) -> float:
    if n == 0 or m == 0:
        return 1.0
    return math.sqrt(-0.5 * math.log(alpha / 2.0)) * math.sqrt((n + m) / (n * m))


class PerformanceGate:
    """Detect statistically significant latency regressions via KS test."""

    def __init__(self, baseline_path: Path | None = None) -> None:
        settings = get_settings()
        self.baseline_path = baseline_path or settings.perf_baseline_path
        self.threshold = 0.05
        self.baseline = _load_samples(self.baseline_path)

    def compare(self, samples: Iterable[float]) -> dict[str, float | bool]:
        candidate = [float(value) for value in samples]
        statistic = _ks_statistic(self.baseline, candidate)
        critical = _critical_value(len(self.baseline), len(candidate))
        regression = statistic > critical
        return {
            "statistic": statistic,
            "critical": critical,
            "regression": regression,
            "baseline_count": float(len(self.baseline)),
            "candidate_count": float(len(candidate)),
        }


def load_gate() -> PerformanceGate:
    return PerformanceGate()

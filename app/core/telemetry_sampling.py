from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque


@dataclass
class SamplingDecision:
    sampled: bool
    reason: str


class AdaptiveSampler:
    """Load-aware telemetry sampler that preserves errors and tail latency."""

    def __init__(
        self,
        *,
        window_seconds: float = 5.0,
        tail_threshold_ms: float = 150.0,
        target_events: int = 250,
        min_rate: float = 0.1,
        max_rate: float = 1.0,
    ) -> None:
        self.window_seconds = window_seconds
        self.tail_threshold_ms = tail_threshold_ms
        self.target_events = target_events
        self.min_rate = min_rate
        self.max_rate = max_rate
        self._events: Deque[float] = deque()

    def _observe(self) -> None:
        now = time.monotonic()
        self._events.append(now)
        horizon = now - self.window_seconds
        while self._events and self._events[0] < horizon:
            self._events.popleft()

    def should_sample(self, latency_ms: float, *, is_error: bool = False) -> SamplingDecision:
        self._observe()
        if is_error:
            return SamplingDecision(sampled=True, reason="error")
        if latency_ms >= self.tail_threshold_ms:
            return SamplingDecision(sampled=True, reason="tail")
        load = len(self._events) / max(self.window_seconds, 1e-6)
        if load <= 1:
            return SamplingDecision(sampled=True, reason="idle")
        desired_rate = min(self.max_rate, max(self.min_rate, self.target_events / max(load, 1e-6)))
        if random.random() <= desired_rate:
            return SamplingDecision(sampled=True, reason="sampled")
        return SamplingDecision(sampled=False, reason="suppressed")

    def summary(self) -> dict[str, float]:
        return {
            "tail_threshold_ms": self.tail_threshold_ms,
            "window_seconds": self.window_seconds,
            "target_events": float(self.target_events),
            "current_rate": len(self._events) / max(self.window_seconds, 1e-6),
        }


_sampler: AdaptiveSampler | None = None


def get_sampler() -> AdaptiveSampler:
    global _sampler
    if _sampler is None:
        _sampler = AdaptiveSampler()
    return _sampler

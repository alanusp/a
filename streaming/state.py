from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean
from typing import Deque

from collections import deque


@dataclass
class ConceptDriftState:
    window: int = 500
    drift_threshold: float = 0.15
    scores: Deque[float] = field(default_factory=deque)

    def update(self, score: float) -> bool:
        self.scores.append(score)
        if len(self.scores) > self.window:
            self.scores.popleft()
        if len(self.scores) < self.window:
            return False
        recent_mean = fmean(list(self.scores)[-self.window // 5 :])
        baseline_mean = fmean(list(self.scores)[: self.window // 5])
        drift = abs(recent_mean - baseline_mean)
        return drift >= self.drift_threshold

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


@dataclass(slots=True)
class ReviewCandidate:
    event_id: str
    probability: float
    amount: float
    review_cost: float

    def expected_loss(self) -> float:
        return self.probability * self.amount


@dataclass(slots=True)
class ReviewDecision:
    event_id: str
    action: str
    expected_value: float


class QueueBudgetOptimizer:
    """Solve a knapsack-style allocation for manual review capacity."""

    def __init__(self, capacity: int) -> None:
        if capacity < 0:
            raise ValueError("Capacity must be non-negative")
        self.capacity = capacity

    def optimise(self, candidates: Sequence[ReviewCandidate]) -> List[ReviewDecision]:
        if self.capacity == 0 or not candidates:
            return [ReviewDecision(candidate.event_id, "auto", -candidate.expected_loss()) for candidate in candidates]
        n = len(candidates)
        capacity = min(self.capacity, n)
        dp = [[0.0] * (capacity + 1) for _ in range(n + 1)]
        keep = [[False] * (capacity + 1) for _ in range(n + 1)]
        baseline_values = [-candidate.expected_loss() for candidate in candidates]
        incremental_values = [
            max(0.0, candidate.expected_loss() - candidate.review_cost)
            for candidate in candidates
        ]
        for i in range(1, n + 1):
            value = incremental_values[i - 1]
            for c in range(1, capacity + 1):
                without = dp[i - 1][c]
                with_item = dp[i - 1][c - 1] + value
                if with_item > without:
                    dp[i][c] = with_item
                    keep[i][c] = True
                else:
                    dp[i][c] = without
        decisions: List[ReviewDecision] = []
        c = capacity
        selected = set()
        for i in range(n, 0, -1):
            if keep[i][c]:
                selected.add(i - 1)
                c -= 1
        for idx, candidate in enumerate(candidates):
            base_value = baseline_values[idx]
            if idx in selected:
                total = base_value + incremental_values[idx]
                decisions.append(ReviewDecision(candidate.event_id, "review", total))
            else:
                decisions.append(ReviewDecision(candidate.event_id, "auto", base_value))
        return decisions

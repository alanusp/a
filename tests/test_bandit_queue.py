from __future__ import annotations

from app.services.bandit import ThresholdBandit
from app.services.queue_budget import QueueBudgetOptimizer, ReviewCandidate


def test_bandit_learns_rewarding_threshold() -> None:
    bandit = ThresholdBandit([0.2, 0.4, 0.6], strategy="ucb")
    for _ in range(50):
        chosen = bandit.recommend("segment")
        reward = 1.0 if chosen <= 0.4 else -0.5
        bandit.observe("segment", chosen, reward=reward, guardrail_ok=True)
    snapshot = bandit.snapshot()
    restored = ThresholdBandit.from_snapshot(snapshot)
    assert restored.recommend("segment") <= 0.4


def test_queue_budget_respects_capacity() -> None:
    optimiser = QueueBudgetOptimizer(capacity=2)
    candidates = [
        ReviewCandidate("e1", 0.8, 100.0, 10.0),
        ReviewCandidate("e2", 0.2, 40.0, 10.0),
        ReviewCandidate("e3", 0.6, 80.0, 10.0),
    ]
    decisions = optimiser.optimise(candidates)
    assert sum(1 for decision in decisions if decision.action == "review") == 2
    assert decisions[0].action == "review"

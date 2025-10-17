from __future__ import annotations

from app.services.fairness import FairnessAdjustment, adjust_thresholds, compute_group_metrics


def test_fairness_adjustment_respects_epsilon() -> None:
    events = [
        ("a", 1, 1),
        ("a", 1, 0),
        ("b", 0, 1),
        ("b", 1, 1),
        ("b", 1, 0),
    ]
    metrics = compute_group_metrics(events)
    adjustment = adjust_thresholds(0.5, metrics, epsilon=0.05)
    assert isinstance(adjustment, FairnessAdjustment)
    assert set(adjustment.thresholds) == {"a", "b"}

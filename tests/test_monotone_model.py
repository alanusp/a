from __future__ import annotations

import random

from app.models.monotone import MonotoneConstraint, MonotoneLogisticRegression
from app.models.online import OnlineLogisticRegression


def test_monotone_projection_preserves_direction() -> None:
    base = OnlineLogisticRegression.from_dimension(2, learning_rate=0.1)
    wrapper = MonotoneLogisticRegression(base, constraints=MonotoneConstraint(increasing=frozenset({0})))
    rng = random.Random(42)
    for _ in range(200):
        x0 = rng.random()
        x1 = rng.random()
        label = 1.0 if x0 + 0.1 * x1 > 0.6 else 0.0
        wrapper.partial_fit([x0, x1], label)
    assert wrapper.verify_monotonicity(0, [0.2, 0.5])
    snapshot = wrapper.snapshot()
    restored = MonotoneLogisticRegression.from_snapshot(snapshot)
    assert restored.verify_monotonicity(0, [0.2, 0.5])

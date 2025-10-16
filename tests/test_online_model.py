from __future__ import annotations

import math

from app.models.online import OnlineLogisticRegression


def _log_loss(probability: float, label: float) -> float:
    probability = min(max(probability, 1e-9), 1.0 - 1e-9)
    return -(
        label * math.log(probability)
        + (1.0 - label) * math.log(1.0 - probability)
    )


def test_online_logistic_regression_reduces_loss():
    model = OnlineLogisticRegression.from_dimension(
        2,
        learning_rate=0.1,
        l2=0.01,
        calibrator_learning_rate=None,
    )
    samples = [
        ([0.0, 0.0], 0.0),
        ([1.0, 0.0], 1.0),
        ([1.0, 1.0], 1.0),
        ([0.0, 1.0], 0.0),
    ]

    def total_loss() -> float:
        return sum(_log_loss(model.predict_proba(features), label) for features, label in samples)

    baseline = total_loss()
    for _ in range(30):
        for features, label in samples:
            model.partial_fit(features, label, calibrate=False)
    trained = total_loss()

    assert trained < baseline

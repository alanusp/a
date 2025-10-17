from __future__ import annotations

from app.models.online import OnlineLogisticRegression


def test_learning_rate_schedule_and_snapshot():
    model = OnlineLogisticRegression.from_dimension(
        3,
        learning_rate=0.5,
        lr_decay=0.5,
        snapshot_interval=2,
    )
    baseline_lr = model.learning_rate
    model.partial_fit([0.1, 0.2, 0.3], 1.0)
    assert model.learning_rate < baseline_lr
    model.partial_fit([0.1, 0.2, 0.3], 0.0)
    assert model.should_snapshot()


def test_drift_freezes_model():
    model = OnlineLogisticRegression.from_dimension(
        2,
        learning_rate=0.2,
        drift_threshold=0.1,
        drift_patience=0,
    )
    before = list(model.weights)
    model.partial_fit([1.0, 1.0], 1.0, drift_score=0.2)
    assert model.frozen is True
    after = list(model.weights)
    assert after == before
    model.resume()
    model.partial_fit([1.0, 1.0], 0.0, drift_score=0.0)
    assert model.frozen is False


def test_calibration_metrics_track_updates():
    model = OnlineLogisticRegression.from_dimension(2, learning_rate=0.1)
    for _ in range(20):
        model.partial_fit([0.2, 0.4], 1.0)
        model.partial_fit([0.1, 0.3], 0.0)
    assert model.brier_score() >= 0.0
    assert 0.0 <= model.expected_calibration_error() <= 1.0

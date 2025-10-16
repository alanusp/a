import random

from app.models.online import OnlineLogisticRegression


def test_conformal_prediction_sets_cover():
    random.seed(42)
    model = OnlineLogisticRegression.from_dimension(
        3,
        learning_rate=0.05,
        calibrator_learning_rate=None,
        target_coverage=0.9,
    )
    for _ in range(256):
        features = [random.random(), random.random(), random.random()]
        label = 1.0 if sum(features) > 1.5 else 0.0
        model.partial_fit(features, label, group="g1" if features[0] > 0.5 else "g2")
    metrics = model.coverage_metrics()
    assert 0.0 <= metrics["coverage"] <= 1.0
    prediction_set = model.predict_set([0.2, 0.2, 0.2])
    assert prediction_set
    fairness = model.fairness_metrics()
    assert set(fairness) == {"tpr_gap", "fpr_gap", "eo_gap"}

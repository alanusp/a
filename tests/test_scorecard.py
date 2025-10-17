from __future__ import annotations

from pathlib import Path

from app.models.online import OnlineLogisticRegression
from app.services.scorecard import BinStat, build_scorecard, compute_woe_iv


def test_scorecard_preserves_order(tmp_path: Path) -> None:
    model = OnlineLogisticRegression.from_dimension(2, calibrator_kind=None)
    model.weights = [0.8, -0.3]
    model.bias = -0.1
    scorecard = build_scorecard(model, ["feature_a", "feature_b"], base_points=500, points_to_double_odds=30)
    samples = [[0.2, 0.1], [0.3, 0.4], [0.1, -0.2]]
    lr_order = sorted(samples, key=model.predict_logit)
    sc_order = sorted(samples, key=scorecard.score)
    assert lr_order == sc_order
    output = tmp_path / "scorecard.csv"
    scorecard.export_csv(output, samples)
    assert output.exists()


def test_compute_woe_iv() -> None:
    stats = [
        BinStat("feature", "low", good=80, bad=20),
        BinStat("feature", "high", good=20, bad=80),
    ]
    results = compute_woe_iv(stats)
    assert len(results) == 2
    assert results[0].information_value > 0

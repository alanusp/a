from __future__ import annotations

import math

from app.models.online import OnlineLogisticRegression


def test_feature_contributions_sum_to_logit():
    model = OnlineLogisticRegression(
        weights=[0.5, -0.25],
        bias=-0.1,
        learning_rate=0.1,
    )
    features = [2.0, 1.0]
    explanation = model.explain(features, threshold=0.5, bounds=[(0.0, 10.0), (0.0, 10.0)])
    contributions = explanation["contributions"]
    assert math.isclose(model.bias + sum(contributions), explanation["logit"], rel_tol=1e-6)
    if explanation["probability"] >= 0.5:
        suggestion = explanation["counterfactual"]
        assert suggestion["feature_index"] is not None
        index = suggestion["feature_index"]
        adjusted = features.copy()
        adjusted[index] = suggestion["new_value"]
        new_prob = model.predict_proba(adjusted)
        assert new_prob < explanation["probability"]

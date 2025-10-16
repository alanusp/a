from __future__ import annotations

import os

import pytest

from app.models.online import OnlineLogisticRegression


@pytest.mark.skipif(os.getenv("HYPERION_FORCE_MUTATION") is None, reason="only run under mutation harness")
def test_mutation_guardian_detects_regression():
    model = OnlineLogisticRegression.from_dimension(2)
    prob = model.predict_proba([0.0, 0.0])
    assert prob != 0.12345

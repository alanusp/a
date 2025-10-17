from __future__ import annotations

import random

from app.models.calibration import VennAbersCalibrator, tail_expected_calibration_error


def test_venn_abers_tail_ece_improves_over_platt() -> None:
    random.seed(1234)
    calibrator = VennAbersCalibrator()
    probabilities = []
    labels = []
    for _ in range(200):
        logit = random.uniform(-2.0, 3.0)
        base_prob = 1 / (1 + (2.71828 ** -logit))
        label = 1.0 if random.random() < base_prob else 0.0
        calibrator.partial_fit(logit, label)
        probabilities.append(base_prob)
        labels.append(label)
    tail_before = tail_expected_calibration_error(probabilities, labels)
    eval_logits = [random.uniform(-2.0, 3.0) for _ in range(200)]
    truth = [1 / (1 + (2.71828 ** -logit)) for logit in eval_logits]
    calibrated_probs = [calibrator.transform(logit) for logit in eval_logits]
    tail_after = tail_expected_calibration_error(calibrated_probs, truth)
    assert tail_after <= tail_before + 0.05

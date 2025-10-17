from __future__ import annotations

import math

from app.models.calibration import IsotonicCalibrator, build_calibrator, load_calibrator


def test_isotonic_calibrator_monotone_and_snapshot() -> None:
    calibrator = IsotonicCalibrator()
    samples = [(-2.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (2.0, 1.0)]
    for logit, label in samples:
        calibrator.partial_fit(logit, label)
    values = [calibrator.transform(logit) for logit in [-3.0, -1.0, 0.0, 2.0]]
    assert values == sorted(values)
    snapshot = calibrator.snapshot()
    restored = load_calibrator(snapshot)
    for logit in [-3.0, -1.0, 0.0, 2.0]:
        assert math.isclose(calibrator.transform(logit), restored.transform(logit), rel_tol=1e-6)


def test_build_calibrator_supports_isotonic() -> None:
    calibrator = build_calibrator("isotonic")
    assert isinstance(calibrator, IsotonicCalibrator)

from __future__ import annotations

from canary.stats import cuped_adjust, sequential_ks, sequential_sprt


def test_cuped_reduces_variance() -> None:
    control = [0.2, 0.21, 0.19, 0.22, 0.2]
    treatment = [0.19, 0.2, 0.18, 0.23, 0.21]
    cov_control = [0.19, 0.2, 0.18, 0.21, 0.2]
    cov_treatment = [0.18, 0.19, 0.17, 0.22, 0.2]
    result = cuped_adjust(control, treatment, control_covariate=cov_control, treatment_covariate=cov_treatment)
    assert result.variance_reduction >= 0.0


def test_sequential_tests_detect_shift() -> None:
    control = [0.2] * 10
    treatment = [0.2] * 5 + [0.35] * 5
    ks_result = sequential_ks(control, treatment, alpha=0.1, beta=0.2)
    assert ks_result.stopped is True
    sprt_result = sequential_sprt(control, treatment, delta=0.05, alpha=0.1, beta=0.2)
    assert sprt_result.stopped is True

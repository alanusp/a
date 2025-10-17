from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(slots=True)
class CupedResult:
    treatment_mean: float
    control_mean: float
    theta: float
    variance_reduction: float


def _mean(values: Sequence[float]) -> float:
    return sum(values) / max(len(values), 1)


def _variance(values: Sequence[float], mean: float | None = None) -> float:
    if not values:
        return 0.0
    mean = _mean(values) if mean is None else mean
    return sum((value - mean) ** 2 for value in values) / len(values)


def _covariance(xs: Sequence[float], ys: Sequence[float]) -> float:
    if not xs or not ys:
        return 0.0
    mean_x = _mean(xs)
    mean_y = _mean(ys)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False)) / len(xs)


def cuped_adjust(
    control: Sequence[float],
    treatment: Sequence[float],
    *,
    control_covariate: Sequence[float],
    treatment_covariate: Sequence[float],
) -> CupedResult:
    if len(control_covariate) != len(control) or len(treatment_covariate) != len(treatment):
        raise ValueError("Metric and covariate lengths must match")
    theta_control = _covariance(control, control_covariate) / max(_variance(control_covariate), 1e-9)
    theta_treatment = _covariance(treatment, treatment_covariate) / max(_variance(treatment_covariate), 1e-9)
    theta = 0.5 * (theta_control + theta_treatment)
    adjusted_control = [
        metric - theta * (cov - _mean(control_covariate))
        for metric, cov in zip(control, control_covariate, strict=False)
    ]
    adjusted_treatment = [
        metric - theta * (cov - _mean(treatment_covariate))
        for metric, cov in zip(treatment, treatment_covariate, strict=False)
    ]
    baseline_variance = 0.5 * (_variance(control) + _variance(treatment))
    adjusted_variance = 0.5 * (_variance(adjusted_control) + _variance(adjusted_treatment))
    reduction = 0.0
    if baseline_variance > 0:
        reduction = max(0.0, 1.0 - adjusted_variance / baseline_variance)
    return CupedResult(
        treatment_mean=_mean(adjusted_treatment),
        control_mean=_mean(adjusted_control),
        theta=theta,
        variance_reduction=reduction,
    )


@dataclass(slots=True)
class SequentialTestResult:
    stopped: bool
    statistic: float
    boundary: float
    reason: str


def sequential_ks(
    control: Sequence[float],
    treatment: Sequence[float],
    *,
    alpha: float = 0.05,
    beta: float = 0.2,
) -> SequentialTestResult:
    if len(control) != len(treatment):
        raise ValueError("Control and treatment samples must align for sequential KS")
    cumulative_control: list[float] = []
    cumulative_treatment: list[float] = []
    base = math.sqrt(max(1e-9, -0.5 * math.log(alpha / 2.0)))
    for index, (c_value, t_value) in enumerate(zip(control, treatment, strict=False), start=1):
        cumulative_control.append(c_value)
        cumulative_treatment.append(t_value)
        statistic = _ks_statistic(cumulative_control, cumulative_treatment)
        boundary = base / math.sqrt(index)
        if statistic > boundary:
            return SequentialTestResult(True, statistic, boundary, "treatment_regression")
    final_boundary = base / math.sqrt(max(len(control), 1))
    return SequentialTestResult(False, _ks_statistic(control, treatment), final_boundary, "continue")


def _ks_statistic(control: Sequence[float], treatment: Sequence[float]) -> float:
    sorted_control = sorted(control)
    sorted_treatment = sorted(treatment)
    index_control = 0
    index_treatment = 0
    cdf_control = 0.0
    cdf_treatment = 0.0
    n_control = len(sorted_control)
    n_treatment = len(sorted_treatment)
    statistic = 0.0
    while index_control < n_control or index_treatment < n_treatment:
        if index_treatment >= n_treatment or (
            index_control < n_control and sorted_control[index_control] <= sorted_treatment[index_treatment]
        ):
            index_control += 1
            cdf_control = index_control / n_control
        else:
            index_treatment += 1
            cdf_treatment = index_treatment / n_treatment
        statistic = max(statistic, abs(cdf_control - cdf_treatment))
    return statistic


def sequential_sprt(
    control: Iterable[float],
    treatment: Iterable[float],
    *,
    delta: float,
    alpha: float = 0.05,
    beta: float = 0.2,
) -> SequentialTestResult:
    threshold_accept = delta
    threshold_reject = -delta
    control_list = list(control)
    treatment_list = list(treatment)
    diff_sum = 0.0
    for index, (c_value, t_value) in enumerate(zip(control_list, treatment_list, strict=False), start=1):
        diff_sum += t_value - c_value
        mean_diff = diff_sum / index
        if mean_diff >= threshold_accept:
            return SequentialTestResult(True, mean_diff, threshold_accept, "accept_improvement")
        if mean_diff <= threshold_reject:
            return SequentialTestResult(True, mean_diff, threshold_reject, "regression")
    total = max(len(control_list), 1)
    return SequentialTestResult(False, diff_sum / total, threshold_accept, "continue")

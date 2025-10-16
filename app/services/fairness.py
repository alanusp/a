from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, Tuple


@dataclass(slots=True)
class GroupMetrics:
    group: str
    tpr: float
    fpr: float


@dataclass(slots=True)
class FairnessAdjustment:
    thresholds: Dict[str, float]
    gaps: Dict[str, float]


def compute_group_metrics(events: Sequence[Tuple[str, int, int]]) -> Dict[str, GroupMetrics]:
    metrics: Dict[str, GroupMetrics] = {}
    for group, prediction, label in events:
        record = metrics.setdefault(group, GroupMetrics(group, 0.0, 0.0))
        if label == 1 and prediction == 1:
            record.tpr += 1.0
        if label == 0 and prediction == 1:
            record.fpr += 1.0
        if label == 1:
            record.tpr += 0.0
        if label == 0:
            record.fpr += 0.0
    totals: Dict[str, Tuple[float, float]] = {}
    for group, prediction, label in events:
        positive, negative = totals.get(group, (0.0, 0.0))
        if label == 1:
            positive += 1.0
        else:
            negative += 1.0
        totals[group] = (positive, negative)
    for group, metric in metrics.items():
        positive, negative = totals.get(group, (1.0, 1.0))
        metric.tpr = metric.tpr / max(positive, 1e-9)
        metric.fpr = metric.fpr / max(negative, 1e-9)
    return metrics


def adjust_thresholds(
    base_threshold: float,
    group_metrics: Dict[str, GroupMetrics],
    *,
    epsilon: float,
) -> FairnessAdjustment:
    thresholds: Dict[str, float] = {}
    max_tpr = max((metric.tpr for metric in group_metrics.values()), default=base_threshold)
    gaps: Dict[str, float] = {}
    for group, metric in group_metrics.items():
        gap = max_tpr - metric.tpr
        if gap <= epsilon:
            thresholds[group] = base_threshold
            gaps[group] = gap
            continue
        thresholds[group] = min(0.99, base_threshold - gap / 2.0)
        gaps[group] = gap
    return FairnessAdjustment(thresholds=thresholds, gaps=gaps)

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import csv

from app.models.online import OnlineLogisticRegression


@dataclass(slots=True)
class Scorecard:
    feature_names: Sequence[str]
    offset: float
    factor: float
    weights: Sequence[float]

    def score(self, features: Sequence[float]) -> float:
        logit = self.offset + sum(self.factor * weight * value for weight, value in zip(self.weights, features, strict=False))
        return logit

    def to_rules(self) -> list[dict[str, float]]:
        return [
            {"feature": name, "weight": weight * self.factor}
            for name, weight in zip(self.feature_names, self.weights, strict=False)
        ]

    def export_csv(self, path: Path, rows: Iterable[Sequence[float]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            header = ["score", *self.feature_names]
            writer.writerow(header)
            for feature_vector in rows:
                writer.writerow([self.score(feature_vector), *feature_vector])


def build_scorecard(
    model: OnlineLogisticRegression,
    feature_names: Sequence[str],
    *,
    base_points: float = 600.0,
    points_to_double_odds: float = 50.0,
) -> Scorecard:
    if len(feature_names) != len(model.weights):
        raise ValueError("Feature names must match model dimension")
    factor = points_to_double_odds / math.log(2)
    offset = base_points - factor * model.bias
    return Scorecard(feature_names=feature_names, offset=offset, factor=factor, weights=list(model.weights))


@dataclass(slots=True)
class BinStat:
    feature: str
    bin_name: str
    good: float
    bad: float


@dataclass(slots=True)
class WoeResult:
    feature: str
    bin_name: str
    woe: float
    information_value: float


def compute_woe_iv(stats: Sequence[BinStat]) -> List[WoeResult]:
    total_good = sum(item.good for item in stats)
    total_bad = sum(item.bad for item in stats)
    results: List[WoeResult] = []
    for item in stats:
        good_ratio = max(item.good / max(total_good, 1e-9), 1e-9)
        bad_ratio = max(item.bad / max(total_bad, 1e-9), 1e-9)
        woe = math.log(good_ratio / bad_ratio)
        iv = (good_ratio - bad_ratio) * woe
        results.append(WoeResult(item.feature, item.bin_name, woe, iv))
    return results

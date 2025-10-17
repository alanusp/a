from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.models.online import OnlineLogisticRegression


@dataclass(slots=True)
class MonotoneConstraint:
    increasing: frozenset[int] = frozenset()
    decreasing: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if self.increasing.intersection(self.decreasing):
            raise ValueError("A feature cannot be both monotone increasing and decreasing")


class MonotoneLogisticRegression:
    """Wrapper around :class:`OnlineLogisticRegression` enforcing monotonic weights."""

    def __init__(
        self,
        base_model: OnlineLogisticRegression,
        *,
        constraints: MonotoneConstraint,
    ) -> None:
        self._model = base_model
        self._constraints = constraints
        self._project_weights()

    @property
    def model(self) -> OnlineLogisticRegression:
        return self._model

    @property
    def constraints(self) -> MonotoneConstraint:
        return self._constraints

    def predict_logit(self, features: Iterable[float]) -> float:
        return self._model.predict_logit(features)

    def predict_proba(self, features: Iterable[float]) -> float:
        return self._model.predict_proba(features)

    def feature_contributions(self, features: Iterable[float]) -> list[float]:
        return self._model.feature_contributions(features)

    def partial_fit(
        self,
        features: Sequence[float],
        label: float,
        *,
        sample_weight: float = 1.0,
        calibrate: bool = True,
        drift_score: float | None = None,
        group: str | None = None,
    ) -> float:
        probability = self._model.partial_fit(
            features,
            label,
            sample_weight=sample_weight,
            calibrate=calibrate,
            drift_score=drift_score,
            group=group,
        )
        self._project_weights()
        return probability

    def _project_weights(self) -> None:
        for index in self._constraints.increasing:
            if self._model.weights[index] < 0.0:
                self._model.weights[index] = 0.0
        for index in self._constraints.decreasing:
            if self._model.weights[index] > 0.0:
                self._model.weights[index] = 0.0

    def verify_monotonicity(
        self,
        feature_index: int,
        baseline: Sequence[float],
        *,
        step: float = 0.1,
        trials: int = 10,
    ) -> bool:
        """Check empirically that monotone features preserve ordering."""

        if feature_index in self._constraints.increasing:
            return self._check_direction(feature_index, baseline, step, trials, increasing=True)
        if feature_index in self._constraints.decreasing:
            return self._check_direction(feature_index, baseline, step, trials, increasing=False)
        raise ValueError("Feature index is not constrained")

    def _check_direction(
        self,
        feature_index: int,
        baseline: Sequence[float],
        step: float,
        trials: int,
        *,
        increasing: bool,
    ) -> bool:
        vector = list(baseline)
        reference = self.predict_proba(vector)
        for _ in range(trials):
            vector[feature_index] += step if increasing else -step
            updated = self.predict_proba(vector)
            if increasing:
                if updated + 1e-9 < reference:
                    return False
            else:
                if updated > reference + 1e-9:
                    return False
            reference = updated
        return True

    def snapshot(self) -> dict[str, object]:
        return {
            "model": self._model.snapshot(),
            "constraints": {
                "increasing": sorted(self._constraints.increasing),
                "decreasing": sorted(self._constraints.decreasing),
            },
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, object]) -> MonotoneLogisticRegression:
        base_snapshot = payload["model"]
        if not isinstance(base_snapshot, dict):
            raise TypeError("Invalid base model snapshot")
        model = OnlineLogisticRegression.from_snapshot(base_snapshot)
        constraint_payload = payload.get("constraints", {})
        increasing = frozenset(int(idx) for idx in constraint_payload.get("increasing", []))
        decreasing = frozenset(int(idx) for idx in constraint_payload.get("decreasing", []))
        constraints = MonotoneConstraint(increasing=increasing, decreasing=decreasing)
        return cls(model, constraints=constraints)

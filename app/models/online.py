from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Sequence
from statistics import fmean
from typing import Deque, Dict, List

from app.models.calibration import (
    Calibrator,
    PlattCalibrator,
    build_calibrator,
    load_calibrator,
    tail_expected_calibration_error,
)
from app.models.model_loader import LogisticModel


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp_neg = math.exp(-value)
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(value)
    return exp_pos / (1.0 + exp_pos)


def _ensure_probability(value: float) -> float:
    return min(max(value, 1e-9), 1.0 - 1e-9)


class OnlineLogisticRegression:
    """Online logistic regression with optional Platt scaling and governance hooks."""

    def __init__(
        self,
        *,
        weights: Sequence[float],
        bias: float,
        learning_rate: float,
        l2: float = 0.0,
        calibrator: Calibrator | None = None,
        lr_decay: float = 0.0,
        min_learning_rate: float = 1e-4,
        snapshot_interval: int | None = None,
        drift_threshold: float | None = None,
        drift_patience: int = 0,
        calibration_window: int = 512,
        conformal_window: int = 512,
        fairness_window: int = 512,
        target_coverage: float = 0.9,
        fairness_threshold: float = 0.5,
    ) -> None:
        self.weights = [float(value) for value in weights]
        self.bias = float(bias)
        self.base_learning_rate = float(learning_rate)
        self.learning_rate = float(learning_rate)
        self.l2 = float(l2)
        self.calibrator = calibrator
        self.steps = 0
        self.lr_decay = float(lr_decay)
        self.min_learning_rate = float(min_learning_rate)
        self.snapshot_interval = snapshot_interval
        self.drift_threshold = drift_threshold
        self.drift_patience = max(int(drift_patience), 0)
        self._drift_violations = 0
        self._frozen = False
        self._last_snapshot_step = 0
        self._calibration: Deque[tuple[float, float]] = deque(maxlen=int(calibration_window))
        self.target_coverage = _ensure_probability(target_coverage)
        self._conformal_scores: Deque[float] = deque(maxlen=int(conformal_window))
        self._coverage_history: Deque[tuple[bool, int]] = deque(maxlen=int(conformal_window))
        self._fairness: Deque[tuple[str | None, float, float]] = deque(maxlen=int(fairness_window))
        self.fairness_threshold = _ensure_probability(fairness_threshold)

    @classmethod
    def from_dimension(
        cls,
        n_features: int,
        *,
        learning_rate: float = 0.05,
        l2: float = 0.0,
        calibrator_kind: str | None = "platt",
        calibrator_learning_rate: float | None = None,
        calibrator_l2: float = 0.0,
        **kwargs: float,
    ) -> OnlineLogisticRegression:
        calibrator: Calibrator | None = None
        if calibrator_kind is not None:
            kind = calibrator_kind.lower()
            if kind == "platt":
                lr = calibrator_learning_rate if calibrator_learning_rate is not None else 0.01
                calibrator = PlattCalibrator(
                    learning_rate=lr,
                    l2=calibrator_l2,
                )
            else:
                calibrator = build_calibrator(kind)
        return cls(
            weights=[0.0] * n_features,
            bias=0.0,
            learning_rate=learning_rate,
            l2=l2,
            calibrator=calibrator,
            **kwargs,
        )

    @classmethod
    def from_static_model(
        cls,
        model: LogisticModel,
        *,
        learning_rate: float = 0.05,
        l2: float = 0.0,
        calibrator_kind: str | None = "platt",
        calibrator_learning_rate: float | None = 0.01,
        calibrator_l2: float = 0.0,
        **kwargs: float,
    ) -> OnlineLogisticRegression:
        calibrator: Calibrator | None = None
        if calibrator_kind is not None:
            kind = calibrator_kind.lower()
            if kind == "platt":
                lr = calibrator_learning_rate if calibrator_learning_rate is not None else 0.01
                calibrator = PlattCalibrator(
                    learning_rate=lr,
                    l2=calibrator_l2,
                )
            else:
                calibrator = build_calibrator(kind)
        return cls(
            weights=model.weights,
            bias=model.bias,
            learning_rate=learning_rate,
            l2=l2,
            calibrator=calibrator,
            **kwargs,
        )

    @property
    def frozen(self) -> bool:
        return self._frozen

    def resume(self) -> None:
        self._frozen = False
        self._drift_violations = 0

    def _apply_learning_rate_schedule(self) -> float:
        if self.lr_decay <= 0:
            return self.learning_rate
        scheduled = self.base_learning_rate / (1.0 + self.lr_decay * max(self.steps, 1))
        self.learning_rate = max(self.min_learning_rate, scheduled)
        return self.learning_rate

    def _check_drift(self, drift_score: float | None) -> None:
        if self.drift_threshold is None or drift_score is None:
            return
        if drift_score < self.drift_threshold:
            self._drift_violations = 0
            return
        self._drift_violations += 1
        if self.drift_patience == 0 or self._drift_violations > self.drift_patience:
            self._frozen = True

    def predict_logit(self, features: Iterable[float]) -> float:
        feature_list = features if isinstance(features, list) else list(features)
        if len(feature_list) != len(self.weights):
            raise ValueError(
                f"Expected {len(self.weights)} features, received {len(feature_list)}"
            )
        return self.bias + sum(
            weight * float(value)
            for weight, value in zip(self.weights, feature_list, strict=False)
        )

    def predict_proba(self, features: Iterable[float]) -> float:
        logit = self.predict_logit(features)
        if self.calibrator is None:
            return _sigmoid(logit)
        return self.calibrator.transform(logit)

    def feature_contributions(self, features: Iterable[float]) -> list[float]:
        feature_vector = list(features)
        if len(feature_vector) != len(self.weights):
            raise ValueError(
                f"Expected {len(self.weights)} features, received {len(feature_vector)}"
            )
        return [weight * float(value) for weight, value in zip(self.weights, feature_vector, strict=False)]

    def explain(
        self,
        features: Iterable[float],
        *,
        threshold: float,
        bounds: Sequence[tuple[float, float]] | None = None,
    ) -> dict[str, object]:
        feature_vector = list(features)
        contributions = self.feature_contributions(feature_vector)
        bias = self.bias
        logit = bias + sum(contributions)
        probability = self.predict_proba(feature_vector)
        counterfactual = self._counterfactual(
            feature_vector,
            threshold=threshold,
            target_action="approve" if probability >= threshold else "block",
            bounds=bounds,
        )
        return {
            "logit": logit,
            "probability": probability,
            "bias": bias,
            "contributions": contributions,
            "counterfactual": counterfactual,
        }

    def _logit_from_threshold(self, threshold: float) -> float:
        threshold = _ensure_probability(threshold)
        return math.log(threshold / (1.0 - threshold))

    def _counterfactual(
        self,
        features: Sequence[float],
        *,
        threshold: float,
        target_action: str,
        bounds: Sequence[tuple[float, float]] | None = None,
    ) -> dict[str, object]:
        if bounds is None:
            bounds = [(0.0, float("inf"))] * len(features)
        current_logit = self.predict_logit(features)
        target_logit = self._logit_from_threshold(threshold)
        if target_action == "approve":
            desired = min(target_logit, current_logit)
        else:
            desired = max(target_logit, current_logit)
        required_delta = desired - current_logit
        best: dict[str, object] | None = None
        for index, (weight, value, limit) in enumerate(zip(self.weights, features, bounds, strict=False)):
            if weight == 0:
                continue
            delta_value = required_delta / weight
            candidate = float(value) + delta_value
            lower, upper = limit
            candidate = min(max(candidate, lower), upper)
            actual_delta = candidate - float(value)
            new_logit = current_logit + weight * actual_delta
            satisfies = (
                new_logit <= target_logit if target_action == "approve" else new_logit >= target_logit
            )
            if not satisfies:
                continue
            cost = abs(actual_delta)
            proposal = {
                "feature_index": index,
                "delta": actual_delta,
                "new_value": candidate,
                "cost": cost,
            }
            if best is None or cost < best["cost"]:
                best = proposal
        return best or {"feature_index": None, "delta": 0.0, "new_value": None, "cost": 0.0}

    def predict_set(
        self,
        features: Iterable[float],
        *,
        coverage: float | None = None,
        method: str = "aps",
    ) -> set[int]:
        _ = method  # Reserved for future extensions; binary APS/TCP identical here.
        probability = self.predict_proba(features)
        threshold = self._conformal_threshold(coverage)
        candidate_scores = {0: probability, 1: 1.0 - probability}
        selected = {label for label, score in candidate_scores.items() if score <= threshold}
        if not selected:
            selected = {1 if probability >= 0.5 else 0}
        return selected

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
        """Perform one SGD step; returns pre-update probability."""

        feature_vector = list(features)
        if len(feature_vector) != len(self.weights):
            raise ValueError(
                f"Expected {len(self.weights)} features, received {len(feature_vector)}"
            )

        logit = self.predict_logit(feature_vector)
        probability = _sigmoid(logit)
        clipped = _ensure_probability(probability)

        if self._frozen:
            self._record_post_update(clipped, float(label), group)
            return clipped

        self._check_drift(drift_score)
        if self._frozen:
            self._record_post_update(clipped, float(label), group)
            return clipped

        error = clipped - label
        scaled_lr = self.learning_rate * sample_weight

        for index, feature in enumerate(feature_vector):
            gradient = error * float(feature) + self.l2 * self.weights[index]
            self.weights[index] -= scaled_lr * gradient
        self.bias -= scaled_lr * (error + self.l2 * self.bias)
        self.steps += 1
        self._apply_learning_rate_schedule()

        if calibrate and self.calibrator is not None:
            self.calibrator.partial_fit(logit, label, sample_weight=sample_weight)

        self._record_post_update(clipped, float(label), group)
        return clipped

    def snapshot(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "weights": list(self.weights),
            "bias": self.bias,
            "learning_rate": self.learning_rate,
            "base_learning_rate": self.base_learning_rate,
            "l2": self.l2,
            "steps": self.steps,
            "lr_decay": self.lr_decay,
            "min_learning_rate": self.min_learning_rate,
            "snapshot_interval": self.snapshot_interval,
            "drift_threshold": self.drift_threshold,
            "drift_patience": self.drift_patience,
            "frozen": self._frozen,
            "target_coverage": self.target_coverage,
            "fairness_threshold": self.fairness_threshold,
        }
        if self.calibrator is not None:
            payload["calibrator"] = self.calibrator.snapshot()
        if self._calibration:
            payload["calibration"] = {
                "brier": self.brier_score(),
                "ece": self.expected_calibration_error(),
            }
        if self._conformal_scores:
            payload["coverage"] = self.coverage_metrics()
        return payload

    @classmethod
    def from_snapshot(cls, payload: dict[str, object]) -> OnlineLogisticRegression:
        calibrator_payload = payload.get("calibrator")
        calibrator: Calibrator | None = None
        if isinstance(calibrator_payload, dict):
            calibrator = load_calibrator(calibrator_payload)  # type: ignore[arg-type]
        weights = [float(value) for value in payload["weights"]]
        model = cls(
            weights=weights,
            bias=float(payload["bias"]),
            learning_rate=float(payload.get("base_learning_rate", payload.get("learning_rate", 0.05))),
            l2=float(payload.get("l2", 0.0)),
            calibrator=calibrator,
            lr_decay=float(payload.get("lr_decay", 0.0)),
            min_learning_rate=float(payload.get("min_learning_rate", 1e-4)),
            snapshot_interval=payload.get("snapshot_interval"),
            drift_threshold=payload.get("drift_threshold"),
            drift_patience=int(payload.get("drift_patience", 0)),
            target_coverage=float(payload.get("target_coverage", 0.9)),
            fairness_threshold=float(payload.get("fairness_threshold", 0.5)),
        )
        model.steps = int(payload.get("steps", 0))
        model.learning_rate = float(payload.get("learning_rate", model.base_learning_rate))
        if payload.get("frozen"):
            model._frozen = True
        return model

    def to_static_model(self) -> LogisticModel:
        return LogisticModel(weights=tuple(self.weights), bias=self.bias)

    def should_snapshot(self) -> bool:
        if self.snapshot_interval is None:
            return False
        if self.steps == self._last_snapshot_step:
            return False
        if self.steps % self.snapshot_interval == 0:
            self._last_snapshot_step = self.steps
            return True
        return False

    def brier_score(self) -> float:
        if not self._calibration:
            return 0.0
        return fmean((prediction - label) ** 2 for prediction, label in self._calibration)

    def expected_calibration_error(self, bins: int = 10) -> float:
        if not self._calibration:
            return 0.0
        bin_totals: List[float] = [0.0] * bins
        bin_counts: List[int] = [0] * bins
        bin_correct: List[float] = [0.0] * bins
        for prediction, label in self._calibration:
            index = min(int(prediction * bins), bins - 1)
            bin_totals[index] += prediction
            bin_correct[index] += label
            bin_counts[index] += 1
        ece = 0.0
        total = len(self._calibration)
        for totals, correct, count in zip(bin_totals, bin_correct, bin_counts, strict=False):
            if count == 0:
                continue
            avg_pred = totals / count
            avg_label = correct / count
            ece += (count / total) * abs(avg_pred - avg_label)
        return ece

    def tail_expected_calibration_error(self, quantile: float = 0.9) -> float:
        if not self._calibration:
            return 0.0
        probabilities = [prediction for prediction, _ in self._calibration]
        labels = [label for _, label in self._calibration]
        return tail_expected_calibration_error(probabilities, labels, quantile=quantile)

    def coverage_metrics(self) -> Dict[str, float]:
        if not self._coverage_history:
            return {"coverage": 0.0, "avg_set_size": 0.0}
        coverage = fmean(1.0 if covered else 0.0 for covered, _ in self._coverage_history)
        avg_set_size = fmean(size for _, size in self._coverage_history)
        return {"coverage": coverage, "avg_set_size": avg_set_size}

    def fairness_metrics(self, threshold: float | None = None) -> Dict[str, float]:
        if threshold is None:
            threshold = self.fairness_threshold
        if not self._fairness:
            return {"tpr_gap": 0.0, "fpr_gap": 0.0, "eo_gap": 0.0}
        stats: Dict[str | None, Dict[str, int]] = {}
        for group, label, probability in self._fairness:
            predicted = 1 if probability >= threshold else 0
            bucket = stats.setdefault(group, {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
            if label >= 0.5:
                if predicted == 1:
                    bucket["tp"] += 1
                else:
                    bucket["fn"] += 1
            else:
                if predicted == 1:
                    bucket["fp"] += 1
                else:
                    bucket["tn"] += 1
        if len(stats) == 1:
            return {"tpr_gap": 0.0, "fpr_gap": 0.0, "eo_gap": 0.0}
        tprs: List[float] = []
        fprs: List[float] = []
        for values in stats.values():
            positives = values["tp"] + values["fn"]
            negatives = values["tn"] + values["fp"]
            tpr = values["tp"] / positives if positives else 0.0
            fpr = values["fp"] / negatives if negatives else 0.0
            tprs.append(tpr)
            fprs.append(fpr)
        tpr_gap = max(tprs) - min(tprs) if tprs else 0.0
        fpr_gap = max(fprs) - min(fprs) if fprs else 0.0
        eo_gap = max(abs(tp - fp) for tp, fp in zip(tprs, fprs, strict=False)) if tprs else 0.0
        return {"tpr_gap": tpr_gap, "fpr_gap": fpr_gap, "eo_gap": eo_gap}

    def optimal_threshold(
        self,
        *,
        cost_false_positive: float,
        cost_false_negative: float,
        cost_true_positive: float = 0.0,
        cost_true_negative: float = 0.0,
    ) -> float:
        denominator = (cost_false_positive - cost_true_negative) + (
            cost_false_negative - cost_true_positive
        )
        if denominator <= 0:
            return 0.5
        threshold = (cost_false_positive - cost_true_negative) / denominator
        return float(min(max(threshold, 1e-3), 1.0 - 1e-3))

    def _record_post_update(self, probability: float, label: float, group: str | None) -> None:
        self._calibration.append((probability, label))
        self._update_conformal(probability, label)
        if group is not None:
            self._fairness.append((group, label, probability))

    def _conformal_threshold(self, coverage: float | None) -> float:
        target = _ensure_probability(coverage if coverage is not None else self.target_coverage)
        scores = list(self._conformal_scores)
        if not scores:
            return 1.0
        sorted_scores = sorted(scores)
        position = int(math.ceil(target * (len(sorted_scores) + 1))) - 1
        position = max(0, min(position, len(sorted_scores) - 1))
        return sorted_scores[position]

    def _update_conformal(self, probability: float, label: float) -> None:
        score = probability if label < 0.5 else 1.0 - probability
        threshold = self._conformal_threshold(None)
        prediction_set = {
            candidate
            for candidate, candidate_score in {0: probability, 1: 1.0 - probability}.items()
            if candidate_score <= threshold
        }
        covered = int(label >= 0.5) in prediction_set
        self._coverage_history.append((covered, len(prediction_set) or 2))
        self._conformal_scores.append(score)

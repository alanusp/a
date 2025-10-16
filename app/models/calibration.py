from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Protocol, Tuple


class Calibrator(Protocol):
    """Protocol implemented by probabilistic calibrators."""

    def transform(self, logit: float) -> float:  # pragma: no cover - protocol
        ...

    def partial_fit(self, logit: float, label: float, sample_weight: float = 1.0) -> None:  # pragma: no cover - protocol
        ...

    def snapshot(self) -> dict[str, float | list[float] | list[list[float]]]:  # pragma: no cover - protocol
        ...


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp_neg = math.exp(-value)
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(value)
    return exp_pos / (1.0 + exp_pos)


@dataclass(slots=True)
class PlattCalibrator:
    """One-dimensional logistic calibrator updated via SGD."""

    weight: float = 1.0
    bias: float = 0.0
    learning_rate: float = 0.01
    l2: float = 0.0
    steps: int = 0

    CALIBRATOR_TYPE = "platt"

    def transform(self, logit: float) -> float:
        calibrated = self.weight * logit + self.bias
        return _sigmoid(calibrated)

    def partial_fit(self, logit: float, label: float, sample_weight: float = 1.0) -> None:
        prediction = self.transform(logit)
        error = prediction - label
        scaled_lr = self.learning_rate * sample_weight
        self.weight -= scaled_lr * (error * logit + self.l2 * self.weight)
        self.bias -= scaled_lr * (error + self.l2 * self.bias)
        self.steps += 1

    def snapshot(self) -> dict[str, float]:
        return {
            "type": self.CALIBRATOR_TYPE,
            "weight": self.weight,
            "bias": self.bias,
            "learning_rate": self.learning_rate,
            "l2": self.l2,
            "steps": float(self.steps),
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, float]) -> PlattCalibrator:
        calibrator = cls(
            weight=float(payload["weight"]),
            bias=float(payload["bias"]),
            learning_rate=float(payload.get("learning_rate", 0.01)),
            l2=float(payload.get("l2", 0.0)),
        )
        calibrator.steps = int(payload.get("steps", 0.0))
        return calibrator


@dataclass(slots=True)
class IsotonicCalibrator:
    """Batch isotonic calibrator trained with the pool-adjacent-violators algorithm."""

    min_probability: float = 1e-6
    max_probability: float = 1.0 - 1e-6
    _samples: List[tuple[float, float, float]] = field(default_factory=list)
    _thresholds: List[float] = field(default_factory=list)
    _values: List[float] = field(default_factory=list)

    CALIBRATOR_TYPE = "isotonic"

    def _fit(self) -> None:
        if not self._samples:
            self._thresholds = []
            self._values = []
            return
        sorted_samples = sorted(self._samples, key=lambda item: item[0])
        blocks: List[tuple[float, float, float, float]] = []
        for probability, label, weight in sorted_samples:
            weight = max(weight, 1e-9)
            blocks.append((weight, label * weight, probability, probability))
            while len(blocks) >= 2:
                w1, y1, min1, max1 = blocks[-2]
                w2, y2, min2, max2 = blocks[-1]
                if y1 / w1 <= y2 / w2:
                    break
                merged_weight = w1 + w2
                merged_y = y1 + y2
                blocks[-2] = (merged_weight, merged_y, min1, max2)
                blocks.pop()
        self._thresholds = []
        self._values = []
        for weight, weighted_sum, start, end in blocks:
            avg = weighted_sum / max(weight, 1e-9)
            avg = min(max(avg, self.min_probability), self.max_probability)
            self._thresholds.append(end)
            self._values.append(avg)

    def partial_fit(self, logit: float, label: float, sample_weight: float = 1.0) -> None:
        probability = _sigmoid(logit)
        clipped_prob = min(max(probability, self.min_probability), self.max_probability)
        self._samples.append((clipped_prob, label, sample_weight))
        self._fit()

    def transform(self, logit: float) -> float:
        if not self._values:
            return min(max(_sigmoid(logit), self.min_probability), self.max_probability)
        probability = min(max(_sigmoid(logit), self.min_probability), self.max_probability)
        for threshold, value in zip(self._thresholds, self._values):
            if probability <= threshold:
                return value
        return self._values[-1]

    def snapshot(self) -> dict[str, float | list[float] | list[list[float]]]:
        return {
            "type": self.CALIBRATOR_TYPE,
            "thresholds": list(self._thresholds),
            "values": list(self._values),
            "samples": [list(item) for item in self._samples],
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, float | list[float] | list[list[float]]]) -> IsotonicCalibrator:
        calibrator = cls()
        calibrator._thresholds = [float(item) for item in payload.get("thresholds", [])]
        calibrator._values = [float(item) for item in payload.get("values", [])]
        calibrator._samples = [
            (float(prob), float(label), float(weight))
            for prob, label, weight in payload.get("samples", [])
        ]
        return calibrator


@dataclass(slots=True)
class VennAbersCalibrator:
    """Implements the pair method for Venn–Abers calibration."""

    min_probability: float = 1e-6
    max_probability: float = 1.0 - 1e-6
    _samples: List[tuple[float, float, float]] = field(default_factory=list)

    CALIBRATOR_TYPE = "venn_abers"

    def partial_fit(self, logit: float, label: float, sample_weight: float = 1.0) -> None:
        probability = _sigmoid(logit)
        clipped = min(max(probability, self.min_probability), self.max_probability)
        self._samples.append((math.log(clipped / (1 - clipped)), label, sample_weight))

    def _build_isotonic(self, extra: Tuple[float, float, float]) -> IsotonicCalibrator:
        calibrator = IsotonicCalibrator()
        for logit, label, weight in self._samples:
            calibrator.partial_fit(logit, label, sample_weight=weight)
        calibrator.partial_fit(extra[0], extra[1], sample_weight=extra[2])
        return calibrator

    def transform(self, logit: float) -> float:
        if not self._samples:
            return _sigmoid(logit)
        lower_cal = self._build_isotonic((logit, 0.0, 1.0))
        upper_cal = self._build_isotonic((logit, 1.0, 1.0))
        lower = lower_cal.transform(logit)
        upper = upper_cal.transform(logit)
        lower = min(max(lower, self.min_probability), self.max_probability)
        upper = min(max(upper, lower), self.max_probability)
        denominator = 1.0 - upper + lower
        if denominator <= 0:
            return upper
        return lower / denominator

    def snapshot(self) -> dict[str, float | list[list[float]]]:
        return {
            "type": self.CALIBRATOR_TYPE,
            "samples": [list(item) for item in self._samples],
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, List[List[float]]]) -> "VennAbersCalibrator":
        calibrator = cls()
        calibrator._samples = [
            (float(logit), float(label), float(weight))
            for logit, label, weight in payload.get("samples", [])
        ]
        return calibrator


def build_calibrator(kind: str | None) -> Calibrator | None:
    if kind is None:
        return None
    normalized = kind.lower()
    if normalized == "platt":
        return PlattCalibrator()
    if normalized == "isotonic":
        return IsotonicCalibrator()
    if normalized in {"venn", "venn_abers"}:
        return VennAbersCalibrator()
    raise ValueError(f"Unsupported calibrator kind: {kind}")


def load_calibrator(payload: dict[str, float | list[float] | list[list[float]]]) -> Calibrator:
    kind = str(payload.get("type", "platt")).lower()
    if kind == "platt":
        return PlattCalibrator.from_snapshot(payload)  # type: ignore[arg-type]
    if kind == "isotonic":
        return IsotonicCalibrator.from_snapshot(payload)
    if kind in {"venn", "venn_abers"}:
        return VennAbersCalibrator.from_snapshot(payload)  # type: ignore[arg-type]
    raise ValueError(f"Unsupported calibrator snapshot type: {kind}")


def tail_expected_calibration_error(
    probabilities: Iterable[float],
    labels: Iterable[float],
    *,
    quantile: float = 0.9,
    bins: int = 10,
) -> float:
    """Compute ECE restricted to the upper ``quantile`` portion of probabilities."""

    paired = sorted(zip(probabilities, labels), key=lambda item: item[0])
    if not paired:
        return 0.0
    threshold_index = int(len(paired) * quantile)
    tail = paired[threshold_index:]
    if not tail:
        tail = paired[-1:]
    bin_size = max(1, len(tail) // bins)
    error = 0.0
    for idx in range(0, len(tail), bin_size):
        bucket = tail[idx : idx + bin_size]
        probs = [item[0] for item in bucket]
        labels_bucket = [item[1] for item in bucket]
        if not probs:
            continue
        avg_prob = sum(probs) / len(probs)
        avg_label = sum(labels_bucket) / len(labels_bucket)
        error += abs(avg_prob - avg_label) * len(bucket) / len(tail)
    return float(error)

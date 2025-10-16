from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

from app.core.config import get_settings


@dataclass
class DriftReport:
    cosine_similarity: float
    bias_delta: float
    calibrator_delta: float
    threshold: float
    within_bounds: bool


class ModelGuard:
    def __init__(self, *, threshold: float | None = None) -> None:
        settings = get_settings()
        self.threshold = threshold or float(settings.model_drift_threshold)
        self.model_path = settings.model_path
        self.calibration_path = getattr(settings, "calibration_path", Path("artifacts/calibration.json"))
        self.candidate_model_path = getattr(
            settings, "model_candidate_path", Path("artifacts/model_state_candidate.json")
        )
        self.candidate_calibration_path = getattr(
            settings, "calibration_candidate_path", Path("artifacts/calibration_candidate.json")
        )

    @staticmethod
    def _load(path: Path) -> Dict[str, object]:
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _weights(payload: Dict[str, object]) -> Tuple[float, ...]:
        weights = payload.get("weights")
        if not isinstance(weights, Iterable):
            raise ValueError("weights missing from model payload")
        return tuple(float(value) for value in weights)

    @staticmethod
    def _bias(payload: Dict[str, object]) -> float:
        return float(payload.get("bias", 0.0))

    @staticmethod
    def _calibration(payload: Dict[str, object]) -> Tuple[float, ...]:
        params = payload.get("parameters", [])
        if not isinstance(params, Iterable):
            return tuple()
        return tuple(float(value) for value in params)

    @staticmethod
    def _cosine(left: Tuple[float, ...], right: Tuple[float, ...]) -> float:
        dot = sum(l * r for l, r in zip(left, right))
        left_norm = math.sqrt(sum(l * l for l in left))
        right_norm = math.sqrt(sum(r * r for r in right))
        if left_norm == 0 or right_norm == 0:
            return 1.0 if left_norm == right_norm else 0.0
        return dot / (left_norm * right_norm)

    def evaluate(self) -> DriftReport:
        baseline_model = self._load(self.model_path)
        candidate_model = self._load(
            self.candidate_model_path if self.candidate_model_path.exists() else self.model_path
        )
        baseline_weights = self._weights(baseline_model)
        candidate_weights = self._weights(candidate_model)
        cosine = self._cosine(baseline_weights, candidate_weights)
        bias_delta = abs(self._bias(baseline_model) - self._bias(candidate_model))

        try:
            baseline_cal = self._load(self.calibration_path)
        except FileNotFoundError:
            baseline_cal = {"parameters": []}
        try:
            candidate_cal = self._load(self.candidate_calibration_path)
        except FileNotFoundError:
            candidate_cal = baseline_cal

        cal_delta = sum(
            abs(b - c)
            for b, c in zip(self._calibration(baseline_cal), self._calibration(candidate_cal))
        )
        within = cosine >= self.threshold
        return DriftReport(
            cosine_similarity=cosine,
            bias_delta=bias_delta,
            calibrator_delta=cal_delta,
            threshold=self.threshold,
            within_bounds=within,
        )


def evaluate_drift() -> DriftReport:
    guard = ModelGuard()
    return guard.evaluate()

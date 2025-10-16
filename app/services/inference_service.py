from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

from app.core.config import get_settings
from app.core.monitoring import LatencyTracker, ThroughputTracker
from app.core.units import milliseconds, quantize_prob
from app.models.model_loader import load_model
from app.models.online import OnlineLogisticRegression
from app.core.startup import get_startup_state
from app.core.telemetry_sampling import get_sampler
from app.core.durability import get_durability_manager


@dataclass
class PredictionResult:
    probability: float
    is_fraud: bool
    latency_ms: float


class InferenceService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model, self.device = load_model()
        self.online_model = OnlineLogisticRegression.from_static_model(
            self.model,
            learning_rate=self.settings.online_learning_rate,
            l2=self.settings.online_l2,
            calibrator_learning_rate=self.settings.calibrator_learning_rate,
            calibrator_l2=self.settings.calibrator_l2,
            lr_decay=self.settings.online_lr_decay,
            min_learning_rate=self.settings.online_min_learning_rate,
            snapshot_interval=self.settings.online_snapshot_interval,
            drift_threshold=self.settings.online_drift_threshold,
            drift_patience=self.settings.online_drift_patience,
            target_coverage=self.settings.target_coverage,
            conformal_window=self.settings.conformal_window,
            fairness_window=self.settings.fairness_window,
        )
        self.latencies = LatencyTracker(sampler=get_sampler())
        self.throughput = ThroughputTracker()
        self.inference_threshold = self.settings.inference_threshold
        durability = get_durability_manager()
        snapshot = durability.latest("online_model")
        if snapshot:
            self.online_model = OnlineLogisticRegression.from_snapshot(snapshot)
        self.model_candidate_path = getattr(
            self.settings, "model_candidate_path", Path("artifacts/model_state_candidate.json")
        )
        self.calibration_candidate_path = getattr(
            self.settings,
            "calibration_candidate_path",
            Path("artifacts/calibration_candidate.json"),
        )

    def predict(self, features: Iterable[float]) -> PredictionResult:
        start = time.perf_counter()
        feature_vector = list(features)
        probability = quantize_prob(self.online_model.predict_proba(feature_vector))
        latency_ms = float(milliseconds(time.perf_counter() - start))
        self.latencies.add(latency_ms)
        self.throughput.mark()
        return PredictionResult(
            probability=probability,
            is_fraud=probability >= self.settings.inference_threshold,
            latency_ms=latency_ms,
        )

    def partial_fit(
        self,
        features: Iterable[float],
        label: float,
        *,
        sample_weight: float = 1.0,
        calibrate: bool = True,
        group: str | None = None,
    ) -> float:
        """Update the online model in place and refresh the cached static weights."""

        feature_vector = list(features)
        probability = quantize_prob(
            self.online_model.partial_fit(
                feature_vector,
                label,
                sample_weight=sample_weight,
                calibrate=calibrate,
                group=group,
            )
        )
        self.model = self.online_model.to_static_model()
        return probability

    def metrics(self) -> Dict[str, float]:
        summary = self.latencies.summary()
        summary["throughput_eps"] = self.throughput.eps()
        summary["online_updates"] = float(self.online_model.steps)
        summary["brier_score"] = self.online_model.brier_score()
        summary["ece"] = self.online_model.expected_calibration_error()
        summary["tail_ece"] = self.online_model.tail_expected_calibration_error()
        summary["frozen"] = 1.0 if self.online_model.frozen else 0.0
        startup = get_startup_state()
        summary["startup_time_ms"] = startup.startup_time_ms
        summary["startup_ready"] = 1.0 if startup.ready else 0.0
        coverage = self.online_model.coverage_metrics()
        fairness = self.online_model.fairness_metrics()
        summary.update(
            {
                "coverage": coverage.get("coverage", 0.0),
                "avg_prediction_set": coverage.get("avg_set_size", 0.0),
                "tpr_gap": fairness.get("tpr_gap", 0.0),
                "fpr_gap": fairness.get("fpr_gap", 0.0),
                "eo_gap": fairness.get("eo_gap", 0.0),
            }
        )
        return summary

    def flush(self, timeout: float) -> None:
        snapshot = self.online_model.snapshot()
        payload = {"weights": list(self.online_model.weights), "bias": self.online_model.bias}
        model_path = Path(self.model_candidate_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        calibrator = snapshot.get("calibrator")
        cal_path = Path(self.calibration_candidate_path)
        cal_path.parent.mkdir(parents=True, exist_ok=True)
        cal_payload = calibrator if isinstance(calibrator, dict) else {}
        cal_path.write_text(json.dumps(cal_payload, indent=2, sort_keys=True), encoding="utf-8")
        durability = get_durability_manager()
        durability.append("online_model", snapshot)

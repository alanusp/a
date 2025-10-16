from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class ModelPerformance:
    auroc: float
    aupr: float
    p95_latency_ms: float
    alert_rate: float


@dataclass(slots=True)
class CanaryThresholds:
    min_auroc: float = 0.8
    min_aupr: float = 0.6
    max_latency_delta_pct: float = 10.0
    max_alert_delta_pct: float = 15.0


@dataclass(slots=True)
class CanaryDecision:
    candidate_version: str
    baseline_version: str
    accepted: bool
    reason: str


class ModelConfigStore(Protocol):
    def get_active_model(self) -> str: ...

    def set_active_model(self, version: str) -> None: ...


class InMemoryModelConfigStore:
    def __init__(self, initial_version: str = "baseline") -> None:
        self._active = initial_version

    def get_active_model(self) -> str:
        return self._active

    def set_active_model(self, version: str) -> None:
        self._active = version


class CanaryOrchestrator:
    def __init__(
        self,
        *,
        thresholds: CanaryThresholds | None = None,
        config_store: ModelConfigStore | None = None,
    ) -> None:
        self.thresholds = thresholds or CanaryThresholds()
        self.config_store = config_store or InMemoryModelConfigStore()

    def evaluate(
        self,
        *,
        candidate_version: str,
        candidate: ModelPerformance,
        baseline_version: str | None = None,
        baseline: ModelPerformance | None = None,
    ) -> CanaryDecision:
        active_version = baseline_version or self.config_store.get_active_model()
        reference = baseline or ModelPerformance(auroc=0.0, aupr=0.0, p95_latency_ms=1.0, alert_rate=0.0)

        if candidate.auroc < self.thresholds.min_auroc:
            return CanaryDecision(
                candidate_version=candidate_version,
                baseline_version=active_version,
                accepted=False,
                reason=f"AUROC {candidate.auroc:.3f} below threshold {self.thresholds.min_auroc:.3f}",
            )
        if candidate.aupr < self.thresholds.min_aupr:
            return CanaryDecision(
                candidate_version=candidate_version,
                baseline_version=active_version,
                accepted=False,
                reason=f"AUPR {candidate.aupr:.3f} below threshold {self.thresholds.min_aupr:.3f}",
            )
        latency_delta = ((candidate.p95_latency_ms / max(reference.p95_latency_ms, 1e-6)) - 1) * 100
        if latency_delta > self.thresholds.max_latency_delta_pct:
            return CanaryDecision(
                candidate_version=candidate_version,
                baseline_version=active_version,
                accepted=False,
                reason=f"p95 latency delta {latency_delta:.2f}% exceeds {self.thresholds.max_latency_delta_pct}%",
            )
        alert_delta = ((candidate.alert_rate - reference.alert_rate) * 100)
        if alert_delta > self.thresholds.max_alert_delta_pct:
            return CanaryDecision(
                candidate_version=candidate_version,
                baseline_version=active_version,
                accepted=False,
                reason=f"alert-rate delta {alert_delta:.2f}% exceeds {self.thresholds.max_alert_delta_pct}%",
            )

        return CanaryDecision(
            candidate_version=candidate_version,
            baseline_version=active_version,
            accepted=True,
            reason="candidate meets guardrails",
        )

    def apply(self, decision: CanaryDecision) -> None:
        if decision.accepted:
            self.config_store.set_active_model(decision.candidate_version)
        else:
            self.config_store.set_active_model(decision.baseline_version)

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from app.core.config import get_settings


@dataclass(slots=True)
class GuardrailDecision:
    state: str
    reasons: List[str]


class SafetySwitch:
    def __init__(self) -> None:
        settings = get_settings()
        self.latency_threshold = settings.latency_budget_ms
        self.ece_threshold = 0.15
        self.psi_threshold = 0.2
        self.error_rate_threshold = 0.01

    def evaluate(
        self,
        *,
        metrics: Dict[str, float],
        drift_metrics: Dict[str, float] | None = None,
        policy_flags: Iterable[str] | None = None,
        tenant_id: str,
    ) -> GuardrailDecision:
        reasons: List[str] = []
        latency = metrics.get("p95", 0.0)
        if latency > self.latency_threshold:
            reasons.append(f"p95 latency {latency:.2f}ms > {self.latency_threshold}")
        ece = metrics.get("ece", 0.0)
        if ece > self.ece_threshold:
            reasons.append(f"ece {ece:.3f} > {self.ece_threshold}")
        error_rate = metrics.get("error_rate", 0.0)
        if error_rate > self.error_rate_threshold:
            reasons.append(f"error rate {error_rate:.4f} > {self.error_rate_threshold}")
        drift = (drift_metrics or {}).get("psi", 0.0)
        if drift > self.psi_threshold:
            reasons.append(f"psi {drift:.3f} > {self.psi_threshold}")
        if policy_flags:
            for flag in policy_flags:
                reasons.append(f"policy:{flag}")
        state = "ALLOW" if not reasons else "REVIEW"
        return GuardrailDecision(state=state, reasons=[f"tenant={tenant_id}"] + reasons)


def get_safety_switch() -> SafetySwitch:
    return SafetySwitch()

from __future__ import annotations

from app.core.guardrails import SafetySwitch


def test_safety_switch_triggers_review():
    switch = SafetySwitch()
    metrics = {"p95": switch.latency_threshold + 10, "ece": switch.ece_threshold + 0.1, "error_rate": 0.02}
    decision = switch.evaluate(metrics=metrics, drift_metrics={"psi": switch.psi_threshold + 0.1}, policy_flags=["rule"], tenant_id="tenant-a")
    assert decision.state == "REVIEW"
    assert any("psi" in reason for reason in decision.reasons)

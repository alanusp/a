from scripts.opa_eval import evaluate_admission, evaluate_decision


def test_admission_policy_allows_known_tenant():
    payload = {"schema_version": "2024-05-01", "request_tenant": "alpha"}
    data = {"config": {"allowed_schema_version": "2024-05-01", "allowed_tenants": ["alpha", "beta"]}}
    decision = evaluate_admission(payload, data)
    assert decision["allow"] is True
    assert not decision["deny"]


def test_decision_override_triggers_on_latency():
    payload = {"metrics": {"p95_latency_ms": 300.0, "alert_rate": 0.05}}
    data = {"thresholds": {"max_latency_ms": 200.0, "max_alert_rate": 0.1}}
    assert evaluate_decision(payload, data) == "override"


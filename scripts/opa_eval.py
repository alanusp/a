from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def evaluate_admission(input_payload: Dict[str, Any], data_payload: Dict[str, Any]) -> Dict[str, Any]:
    config = data_payload.get("config", {})
    allowed_version = config.get("allowed_schema_version")
    allowed_tenants = set(config.get("allowed_tenants", []))
    allow = input_payload.get("schema_version") == allowed_version and (
        input_payload.get("request_tenant") in allowed_tenants
    )
    deny = []
    if input_payload.get("schema_version") != allowed_version:
        deny.append("schema_version mismatch")
    return {"allow": allow, "deny": deny}


def evaluate_decision(input_payload: Dict[str, Any], data_payload: Dict[str, Any]) -> str:
    thresholds = data_payload.get("thresholds", {})
    metrics = input_payload.get("metrics", {})
    if metrics.get("p95_latency_ms", 0.0) > thresholds.get("max_latency_ms", float("inf")):
        return "override"
    if metrics.get("alert_rate", 0.0) > thresholds.get("max_alert_rate", float("inf")):
        return "override"
    return "model"


def run_suite() -> None:
    admission = evaluate_admission(
        {"schema_version": "2024-05-01", "request_tenant": "public"},
        {"config": {"allowed_schema_version": "2024-05-01", "allowed_tenants": ["public"]}},
    )
    assert admission["allow"] is True
    override = evaluate_decision(
        {"metrics": {"p95_latency_ms": 200.0, "alert_rate": 0.01}},
        {"thresholds": {"max_latency_ms": 150.0, "max_alert_rate": 0.02}},
    )
    assert override == "override"
    print(json.dumps({"admission": admission, "decision": override}))


if __name__ == "__main__":  # pragma: no cover
    run_suite()


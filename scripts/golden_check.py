#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.decision import DecisionService
from app.services.feature_service import FeatureService
from app.services.graph_features import GraphFeatureService
from app.services.inference_service import InferenceService
from streaming.pipeline import compose_event_id

GOLDEN_DIR = Path("artifacts/golden")
PREDICT_FILE = GOLDEN_DIR / "predict.json"
STREAM_FILE = GOLDEN_DIR / "stream.json"

DEFAULT_REQUEST: Dict[str, Any] = {
    "transaction_id": "txn-golden-001",
    "customer_id": "cust-001",
    "merchant_id": "mrc-001",
    "device_id": "dev-001",
    "card_id": "card-001",
    "ip_address": "203.0.113.1",
    "amount": 123.45,
    "currency": "USD",
    "device_trust_score": 0.6,
    "merchant_risk_score": 0.4,
    "velocity_1m": 2.0,
    "velocity_1h": 5.0,
    "chargeback_rate": 0.02,
    "account_age_days": 400.0,
    "customer_tenure": 540.0,
    "geo_distance": 15.0,
    "segment": "retail",
}


def _canonical_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _predict_snapshot(request: Dict[str, Any]) -> Dict[str, Any]:
    feature_service = FeatureService()
    inference_service = InferenceService()
    decision_service = DecisionService(inference_service)
    features = feature_service.to_feature_list(request)
    probability = inference_service.online_model.predict_proba(features)
    prediction_set = inference_service.online_model.predict_set(features)
    decision = decision_service.decide(
        probability=probability,
        features=features,
        context={**request, "tenant_id": "golden"},
        prediction_set=prediction_set,
    )
    snapshot = {
        "probability": probability,
        "decision": decision.action,
        "expected_cost": decision.expected_cost,
        "threshold": decision.threshold,
        "prediction_set": sorted(prediction_set),
    }
    return snapshot


def _stream_snapshot(request: Dict[str, Any]) -> Dict[str, Any]:
    feature_service = FeatureService()
    inference_service = InferenceService()
    graph_service = GraphFeatureService()
    features = feature_service.to_feature_list(request)
    probability = inference_service.online_model.predict_proba(features)
    graph_metrics = graph_service.compute_features(request)
    event_id = compose_event_id(request)
    snapshot = {
        "event_id": event_id,
        "probability": probability,
        "graph_metrics": {key: graph_metrics.get(key, 0.0) for key in graph_service.feature_names},
    }
    return snapshot


def _load_request(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return DEFAULT_REQUEST.copy()
    data = json.loads(path.read_text(encoding="utf-8"))
    request = data.get("request")
    if isinstance(request, dict):
        return request
    return DEFAULT_REQUEST.copy()


def _write_snapshot(path: Path, request: Dict[str, Any], response: Dict[str, Any]) -> None:
    payload = {
        "request": request,
        "response": response,
        "hash": _canonical_hash(response),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_snapshot(path: Path, response: Dict[str, Any]) -> None:
    if not path.exists():
        raise SystemExit(f"golden snapshot missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    expected_hash = data.get("hash")
    actual_hash = _canonical_hash(response)
    if expected_hash != actual_hash:
        raise SystemExit(f"golden drift detected for {path.name}: {actual_hash} != {expected_hash}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate golden inference snapshots")
    parser.add_argument("--approve", action="store_true", help="Refresh golden baselines")
    args = parser.parse_args()

    predict_request = _load_request(PREDICT_FILE)
    predict_response = _predict_snapshot(predict_request)
    stream_request = _load_request(STREAM_FILE)
    stream_response = _stream_snapshot(stream_request)

    if args.approve:
        _write_snapshot(PREDICT_FILE, predict_request, predict_response)
        _write_snapshot(STREAM_FILE, stream_request, stream_response)
        print("golden baselines updated")
        return

    _validate_snapshot(PREDICT_FILE, predict_response)
    _validate_snapshot(STREAM_FILE, stream_response)
    report = {
        "predict_hash": _canonical_hash(predict_response),
        "stream_hash": _canonical_hash(stream_response),
    }
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (GOLDEN_DIR / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("golden snapshots verified")


if __name__ == "__main__":
    main()

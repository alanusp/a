from __future__ import annotations

import json
import sys
from datetime import datetime

import httpx


PAYLOAD = {
    "transaction_id": "probe-1",
    "customer_id": "synthetic",
    "merchant_id": "synthetic",
    "amount": 10.0,
    "currency": "USD",
    "device_trust_score": 0.5,
    "merchant_risk_score": 0.5,
    "velocity_1m": 1.0,
    "velocity_1h": 1.0,
    "chargeback_rate": 0.1,
    "account_age_days": 30,
    "customer_tenure": 12,
    "geo_distance": 100.0,
}


def main() -> None:
    url = "http://localhost:8000/v1/predict"
    with httpx.Client(timeout=2.0) as client:
        response = client.post(url, json=PAYLOAD)
        response.raise_for_status()
        data = response.json()
        print(json.dumps({"timestamp": datetime.utcnow().isoformat(), "status": "ok", "response": data}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - probe should fail loudly
        print(json.dumps({"status": "error", "detail": str(exc)}))
        sys.exit(1)


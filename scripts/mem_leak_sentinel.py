from __future__ import annotations

import argparse
import tracemalloc

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.feature_service import FeatureService
from app.services.inference_service import InferenceService


SAMPLE_PAYLOAD = {
    "transaction_id": "leak-1",
    "customer_id": "cust-leak",
    "merchant_id": "merchant-leak",
    "device_id": "device-leak",
    "card_id": "card-leak",
    "ip_address": "127.0.0.1",
    "amount": 9.99,
    "currency": "USD",
    "device_trust_score": 0.5,
    "merchant_risk_score": 0.5,
    "velocity_1m": 0.0,
    "velocity_1h": 0.0,
    "chargeback_rate": 0.0,
    "account_age_days": 30,
    "customer_tenure": 30,
    "geo_distance": 1.0,
}


def run(threshold_kb: int) -> int:
    feature_service = FeatureService()
    inference_service = InferenceService()
    features = feature_service.to_feature_list(SAMPLE_PAYLOAD)

    tracemalloc.start()
    for _ in range(25):
        inference_service.predict(features)
    baseline = tracemalloc.take_snapshot()
    for _ in range(200):
        inference_service.predict(features)
    comparison = tracemalloc.take_snapshot().compare_to(baseline, "filename")
    total_diff = sum(stat.size_diff for stat in comparison)
    tracemalloc.stop()
    if total_diff > threshold_kb * 1024:
        print(f"memory growth {total_diff / 1024:.1f}KiB exceeds threshold {threshold_kb}KiB")
        return 1
    print(f"memory growth {total_diff / 1024:.1f}KiB within threshold {threshold_kb}KiB")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect memory growth after steady-state warmup")
    parser.add_argument("--threshold", type=int, default=256, help="Allowed memory increase in KiB")
    args = parser.parse_args()
    return run(args.threshold)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

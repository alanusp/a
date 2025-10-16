from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.feature_service import FeatureService
from app.services.inference_service import InferenceService


SLO_P50 = 50.0
SLO_P95 = 150.0


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    values.sort()
    k = (len(values) - 1) * percent
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return d0 + d1


def main() -> int:
    feature_service = FeatureService()
    inference_service = InferenceService()
    payload = {
        "amount": 10.0,
        "customer_tenure": 45.0,
        "device_trust_score": 0.3,
        "merchant_risk_score": 0.2,
        "velocity_1m": 1.0,
        "velocity_1h": 2.0,
        "chargeback_rate": 0.1,
        "account_age_days": 120,
        "geo_distance": 300.0,
    }
    features = feature_service.to_feature_list(payload)
    latencies: list[float] = []
    for _ in range(200):
        start = time.perf_counter()
        inference_service.predict(features)
        latencies.append((time.perf_counter() - start) * 1_000)

    p50 = percentile(latencies, 0.50)
    p95 = percentile(latencies, 0.95)
    if p50 > SLO_P50 or p95 > SLO_P95:
        print(f"SLO violation: p50={p50:.2f}ms p95={p95:.2f}ms", file=sys.stderr)
        return 1
    print(f"SLO ok: p50={p50:.2f}ms p95={p95:.2f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

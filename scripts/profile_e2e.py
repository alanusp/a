from __future__ import annotations

import json
import time
from pathlib import Path

from app.services.feature_service import FeatureService
from app.services.inference_service import InferenceService


def profile() -> Path:
    feature_service = FeatureService()
    inference_service = InferenceService()
    features = feature_service.to_feature_list(
        {
            "amount": 1.0,
            "customer_tenure": 5.0,
            "device_trust_score": 0.5,
            "merchant_risk_score": 0.4,
            "velocity_1m": 1.0,
            "velocity_1h": 0.2,
            "chargeback_rate": 0.05,
            "account_age_days": 30,
            "geo_distance": 100.0,
        }
    )

    samples: list[float] = []
    for _ in range(128):
        start = time.perf_counter()
        inference_service.predict(features)
        samples.append((time.perf_counter() - start) * 1_000)

    output = Path("artifacts/profile.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    sorted_samples = sorted(samples)
    payload = {
        "p50_ms": sorted_samples[len(sorted_samples) // 2],
        "p95_ms": sorted_samples[int(len(sorted_samples) * 0.95)],
        "samples": samples,
    }
    output.write_text(json.dumps(payload, indent=2))
    return output


if __name__ == "__main__":  # pragma: no cover
    print(profile())

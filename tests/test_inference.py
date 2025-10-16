from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.feature_service import FeatureService
from app.services.inference_service import InferenceService


def test_inference_probability_bounds():
    feature_service = FeatureService()
    inference_service = InferenceService()

    payload = {
        "amount": 5.0,
        "customer_tenure": 60.0,
        "device_trust_score": 0.2,
        "merchant_risk_score": 0.9,
        "velocity_1m": 3.0,
        "velocity_1h": 2.5,
        "chargeback_rate": 0.2,
        "account_age_days": 30,
        "geo_distance": 500.0,
        "customer_id": "cust-1",
        "merchant_id": "m-1",
        "device_id": "dev-1",
        "card_id": "card-1",
        "ip_address": "1.1.1.1",
    }

    features = feature_service.to_feature_list(payload)
    result = inference_service.predict(features)

    assert 0.0 <= result.probability <= 1.0
    assert result.probability == pytest.approx(result.probability, rel=0, abs=1e-6)


def test_online_partial_fit_increases_positive_probability():
    feature_service = FeatureService()
    inference_service = InferenceService()

    payload = {
        "amount": 5.0,
        "customer_tenure": 60.0,
        "device_trust_score": 0.2,
        "merchant_risk_score": 0.9,
        "velocity_1m": 3.0,
        "velocity_1h": 2.5,
        "chargeback_rate": 0.2,
        "account_age_days": 30,
        "geo_distance": 500.0,
        "customer_id": "cust-1",
        "merchant_id": "m-1",
        "device_id": "dev-1",
        "card_id": "card-1",
        "ip_address": "1.1.1.1",
    }

    features = feature_service.to_feature_list(payload)
    baseline = inference_service.predict(features).probability

    for _ in range(200):
        inference_service.partial_fit(features, 1.0)

    updated = inference_service.predict(features).probability
    assert updated > baseline


def test_inference_flush_persists_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_path = tmp_path / "model.json"
    cal_path = tmp_path / "cal.json"
    monkeypatch.setenv("MODEL_CANDIDATE_PATH", str(model_path))
    monkeypatch.setenv("CALIBRATION_CANDIDATE_PATH", str(cal_path))
    get_settings.cache_clear()
    try:
        service = InferenceService()
        service.flush(timeout=1.0)
    finally:
        get_settings.cache_clear()
    assert model_path.exists()
    assert cal_path.exists()

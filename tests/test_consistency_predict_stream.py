import pytest

FASTAPI_AVAILABLE = True
try:
    import fastapi  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI unavailable")

from datetime import datetime

from app.services.feature_service import FeatureService
from app.services.inference_service import InferenceService
from streaming.pipeline import enrich_with_prediction


def test_predict_and_stream_consistency() -> None:
    feature_service = FeatureService()
    inference_service = InferenceService()

    payload = {
        "transaction_id": "consistency-1",
        "customer_id": "cust-9",
        "merchant_id": "merchant-9",
        "device_id": "device-9",
        "card_id": "card-9",
        "ip_address": "10.0.0.1",
        "amount": 33.0,
        "currency": "USD",
        "device_trust_score": 0.6,
        "merchant_risk_score": 0.4,
        "velocity_1m": 0.2,
        "velocity_1h": 0.5,
        "chargeback_rate": 0.05,
        "account_age_days": 365,
        "customer_tenure": 720,
        "geo_distance": 5.0,
        "event_id": "consistency-1",
        "ingested_at": datetime.utcnow().isoformat(),
    }

    offline_features = feature_service.to_feature_list(payload)
    offline_prediction = inference_service.predict(offline_features)

    enriched = enrich_with_prediction(dict(payload))
    stream_probability = float(enriched["fraud_probability"])
    stream_action = bool(enriched["is_fraud"])

    assert abs(offline_prediction.probability - stream_probability) <= 1e-6
    assert offline_prediction.is_fraud == stream_action

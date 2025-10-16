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


def _sample_payload() -> dict[str, object]:
    return {
        "transaction_id": "txn-1",
        "customer_id": "cust-1",
        "merchant_id": "m-1",
        "device_id": "device-1",
        "card_id": "card-1",
        "ip_address": "1.1.1.1",
        "amount": 19.95,
        "currency": "USD",
        "device_trust_score": 0.5,
        "merchant_risk_score": 0.2,
        "velocity_1m": 1.0,
        "velocity_1h": 5.0,
        "chargeback_rate": 0.1,
        "account_age_days": 90.0,
        "customer_tenure": 180.0,
        "geo_distance": 25.0,
        "segment": "public",
        "event_id": "seed-event",
        "ingested_at": datetime.utcnow().isoformat(),
    }


def test_online_offline_feature_parity() -> None:
    feature_service = FeatureService()
    inference_service = InferenceService()

    payload = _sample_payload()
    offline_features = feature_service.to_feature_list(payload)
    offline_prob = inference_service.predict(offline_features).probability

    enriched = enrich_with_prediction(dict(payload))
    online_prob = float(enriched["fraud_probability"])

    assert len(offline_features) == len(feature_service.to_feature_list(enriched))
    assert abs(online_prob - offline_prob) <= 1e-6

from datetime import datetime, timedelta

from app.services.feature_service import FeatureService
from app.services.feedback import FeedbackService
from app.services.inference_service import InferenceService


def test_feedback_updates_model(tmp_path):
    feedback = FeedbackService(store_path=tmp_path / "feedback.json")
    inference = InferenceService()
    features = FeatureService().to_feature_list(
        {
            "amount": 15.0,
            "customer_tenure": 12.0,
            "device_trust_score": 0.3,
            "merchant_risk_score": 0.6,
            "velocity_1m": 1.0,
            "velocity_1h": 0.5,
            "chargeback_rate": 0.1,
            "account_age_days": 60,
            "geo_distance": 200.0,
            "customer_id": "cust-1",
            "merchant_id": "m-1",
            "device_id": "dev-1",
            "card_id": "card-1",
            "ip_address": "1.1.1.1",
        }
    )
    baseline = inference.predict(features).probability
    event_id = feedback.register_prediction(
        event_id="evt-1",
        features=features,
        probability=baseline,
        occurred_at=datetime.utcnow(),
        group="segment-a",
        tenant_id="tenant-a",
    )
    result = feedback.record_feedback(
        event_id=event_id,
        label=1.0,
        observed_at=datetime.utcnow() + timedelta(hours=2),
        group="segment-a",
        tenant_id="tenant-a",
    )
    assert result.applied
    inference.partial_fit(
        result.features or features,
        result.label,
        sample_weight=result.sample_weight,
        group=result.group,
    )
    updated = inference.predict(features).probability
    assert updated > baseline

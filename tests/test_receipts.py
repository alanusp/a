import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from app.api.routes import get_decision_service
from app.core.config import get_settings
from app.main import create_application
from app.services.decision import DecisionOutcome
from app.services.policy import PolicyDecision


class StubDecisionService:
    def decide(self, *, probability, features, context, prediction_set, strategy="consensus"):
        return DecisionOutcome(
            action="deny",
            probability=probability,
            prediction_set=set(),
            threshold=0.5,
            reasons=["stub"],
            expected_cost=1.0,
            policy=PolicyDecision(action="deny", matched_rules=["stub"], reasons=["stub"], strategy=strategy),
        )


def test_decision_receipt_header(monkeypatch, tmp_path):
    monkeypatch.setenv("TENANT_API_KEYS", "tenant-alpha:alpha")
    monkeypatch.setenv("DSAR_DIRECTORY", str(tmp_path / "dsar"))
    monkeypatch.setenv("CONSENT_STATE_PATH", str(tmp_path / "consent.txt"))
    monkeypatch.setenv("PRIVACY_SALT_PATH", str(tmp_path / "salt.key"))
    get_settings.cache_clear()
    app = create_application()
    app.dependency_overrides[get_decision_service] = lambda: StubDecisionService()
    try:
        client = TestClient(app)
        payload = {
            "transaction_id": "txn",
            "customer_id": "cust",
            "merchant_id": "merchant",
            "device_id": "device",
            "card_id": "card",
            "ip_address": "1.1.1.1",
            "amount": 20.0,
            "currency": "USD",
            "device_trust_score": 0.1,
            "merchant_risk_score": 0.9,
            "velocity_1m": 5.0,
            "velocity_1h": 10.0,
            "chargeback_rate": 0.2,
            "account_age_days": 10,
            "customer_tenure": 120,
            "geo_distance": 100.0,
        }
        headers = {"x-api-key": "tenant-alpha"}
        response = client.post("/v1/predict", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert "X-Decision-Receipt" in response.headers
        assert "X-Decision-Receipt-Id" in response.headers
        body = response.json()
        assert body.get("receipt_id")
    finally:
        get_settings.cache_clear()

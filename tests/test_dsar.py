from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from app.core.config import get_settings
from app.main import create_application
from app.services.privacy import PrivacyService

TestClient = pytest.importorskip("fastapi.testclient").TestClient


@pytest.fixture(autouse=True)
def configure_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DSAR_DIRECTORY", str(tmp_path / "dsar"))
    monkeypatch.setenv("CONSENT_STATE_PATH", str(tmp_path / "consent.txt"))
    monkeypatch.setenv("PRIVACY_SALT_PATH", str(tmp_path / "salt.key"))
    monkeypatch.setenv("TENANT_API_KEYS", "tenant-alpha:alpha")
    monkeypatch.setenv("MODEL_INPUT_DIM", "16")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _prediction_payload() -> dict[str, object]:
    return {
        "transaction_id": "txn-100",
        "customer_id": "cust-1",
        "merchant_id": "m-1",
        "device_id": "dev-1",
        "card_id": "card-1",
        "ip_address": "1.1.1.1",
        "amount": 12.0,
        "currency": "USD",
        "device_trust_score": 0.4,
        "merchant_risk_score": 0.2,
        "velocity_1m": 1.0,
        "velocity_1h": 1.5,
        "chargeback_rate": 0.1,
        "account_age_days": 30,
        "customer_tenure": 90,
        "geo_distance": 200.0,
    }


def test_dsar_export_and_delete(tmp_path):
    app = create_application()
    client = TestClient(app)
    headers = {"x-api-key": "tenant-alpha"}

    response = client.post("/v1/predict", json=_prediction_payload(), headers=headers)
    assert response.status_code == 200, response.text

    export = client.post(
        "/v1/dsar/export",
        json={"subject_id": "cust-1"},
        headers=headers,
    )
    assert export.status_code == 200
    data = export.json()
    assert data["records"], "Expected DSAR export to return records"

    delete = client.post(
        "/v1/dsar/delete",
        json={"subject_id": "cust-1"},
        headers=headers,
    )
    assert delete.status_code == 200
    receipt = delete.json()
    assert receipt["status"] == "deleted"
    assert "certificate" in receipt
    assert Path(receipt["certificate"]).exists()

    export_again = client.post(
        "/v1/dsar/export",
        json={"subject_id": "cust-1"},
        headers=headers,
    )
    assert export_again.json()["records"] == []


def test_consent_update(tmp_path):
    app = create_application()
    client = TestClient(app)
    headers = {"x-api-key": "tenant-alpha"}

    initial = client.get("/v1/consent", headers=headers)
    assert initial.status_code == 200
    update = client.post("/v1/consent", json={"version": "v2"}, headers=headers)
    assert update.status_code == 200
    assert update.json()["version"] == "v2"

    again = client.get("/v1/consent", headers=headers)
    assert again.json()["version"] == "v2"


def test_legal_hold_blocks_delete(tmp_path):
    app = create_application()
    client = TestClient(app)
    headers = {"x-api-key": "tenant-alpha"}

    service = PrivacyService()
    service.apply_legal_hold(
        tenant_id="tenant-alpha",
        subject_id="cust-1",
        reason="investigation",
        expires_at=datetime.utcnow() + timedelta(days=1),
    )

    response = client.post("/v1/predict", json=_prediction_payload(), headers=headers)
    assert response.status_code == 200

    delete = client.post(
        "/v1/dsar/delete",
        json={"subject_id": "cust-1"},
        headers=headers,
    )
    assert delete.json()["status"] == "legal_hold"

from __future__ import annotations

import hmac
import time
from hashlib import sha256

import pytest

pytest.importorskip("fastapi")

from app.api.routes import get_ingest_signer, get_redis_stream
from app.core.config import get_settings
from app.core.ingest_signing import IngestSigner
from app.main import create_application

TestClient = pytest.importorskip("fastapi.testclient").TestClient


class DummyRedis:
    def __init__(self) -> None:
        self.values: dict[str, float] = {}

    def setnx(self, key: str, value: str) -> bool:
        if key in self.values:
            return False
        self.values[key] = float(value)
        return True

    def expire(self, key: str, ttl: int) -> None:
        self.values[key] = self.values.get(key, 0.0) + ttl


class DummyStream:
    def publish(self, data):  # pragma: no cover - trivial
        self.last = data
        return "ok"


@pytest.fixture
def signer():
    dummy = DummyRedis()
    signer = IngestSigner(secret="secret", redis_client=dummy)
    return signer


@pytest.fixture(autouse=True)
def configure_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TENANT_API_KEYS", "tenant-alpha:alpha")
    monkeypatch.setenv("MODEL_INPUT_DIM", "16")
    monkeypatch.setenv("DSAR_DIRECTORY", str(tmp_path / "dsar"))
    monkeypatch.setenv("CONSENT_STATE_PATH", str(tmp_path / "consent.txt"))
    monkeypatch.setenv("PRIVACY_SALT_PATH", str(tmp_path / "salt.key"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _headers(secret: str, nonce: str, transaction_id: str) -> dict[str, str]:
    timestamp = str(time.time())
    message = f"{nonce}.{timestamp}.{transaction_id}".encode()
    signature = hmac.new(secret.encode(), message, sha256).hexdigest()
    return {
        "x-ingest-signature": signature,
        "x-ingest-nonce": nonce,
        "x-ingest-timestamp": timestamp,
    }


def test_ingest_endpoint(signer):
    app = create_application()
    dummy_stream = DummyStream()
    app.dependency_overrides[get_ingest_signer] = lambda: signer
    from app.api.routes import get_redis_stream

    app.dependency_overrides[get_redis_stream] = lambda: dummy_stream

    client = TestClient(app)
    payload = {
        "transaction_id": "txn-200",
        "customer_id": "cust-9",
        "merchant_id": "m-9",
        "device_id": "dev-9",
        "card_id": "card-9",
        "ip_address": "1.2.3.4",
        "amount": 42.0,
        "currency": "USD",
        "device_trust_score": 0.5,
        "merchant_risk_score": 0.2,
        "velocity_1m": 1.0,
        "velocity_1h": 1.0,
        "chargeback_rate": 0.0,
        "account_age_days": 10,
        "customer_tenure": 20,
        "geo_distance": 100.0,
    }
    headers = _headers("secret", "nonce-1", payload["transaction_id"])
    headers["x-api-key"] = "tenant-alpha"

    response = client.post("/v1/ingest", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    # nonce reuse should fail
    response2 = client.post("/v1/ingest", json=payload, headers=headers)
    assert response2.status_code == 401

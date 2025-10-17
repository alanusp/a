from __future__ import annotations

from app.core import disk_guard, durability
from app.core.config import get_settings
from app.services import idempotency
from app.services.idempotency import IdempotencyStore


def test_idempotency_store_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("WAL_DIRECTORY", str(tmp_path / "wal"))
    get_settings.cache_clear()  # type: ignore[attr-defined]
    durability._MANAGER = None  # type: ignore[attr-defined]
    disk_guard._GUARD = None  # type: ignore[attr-defined]
    idempotency._STORE = None  # type: ignore[attr-defined]
    store = IdempotencyStore()
    assert store._durability.base_path == tmp_path / "wal"  # type: ignore[attr-defined]
    store._durability.truncate("idempotency")  # type: ignore[attr-defined]
    store._cache.clear()  # type: ignore[attr-defined]
    assert store.get("tenant", "key") is None
    payload = {"decision": "approve", "probability": 0.9}
    store.set("tenant", "key", payload, "baseline")
    record = store.get("tenant", "key")
    assert record is not None
    assert record.payload == payload
    assert record.route == "baseline"
    assert record.status_code == 200
    assert record.headers == {}

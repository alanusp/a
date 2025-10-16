from __future__ import annotations

from app.core.config import get_settings
from app.core.leadership import LeaderElector
from app.services.migration import MigrationService, set_migration_service
from streaming.pipeline import build_dual_write_records


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, nx: bool = False, px: int | None = None) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def pexpire(self, key: str, px: int) -> bool:
        return key in self.store

    def delete(self, key: str) -> int:
        if key in self.store:
            del self.store[key]
            return 1
        return 0


def test_cross_version_idempotency_consistency(monkeypatch) -> None:
    monkeypatch.setenv("DUAL_WRITE_ENABLED", "1")
    monkeypatch.setenv("SCORED_TOPIC_VERSION", "1")
    monkeypatch.setenv("SCORED_TOPIC_NEXT_VERSION", "2")
    get_settings.cache_clear()
    leader = LeaderElector(role="migration", client=FakeRedis(), ttl_seconds=1.0)
    set_migration_service(MigrationService(leader=leader))
    payload = {
        "event_id": "evt-123",
        "transaction_id": "txn-123",
        "customer_id": "cust",
        "merchant_id": "m",
        "amount": 99.5,
        "idempotency_key": "idem-1",
    }
    records = build_dual_write_records(payload)
    versions = {record["version"] for record in records}
    assert len(records) == 2
    assert versions == {1, 2}
    keys = {record["idempotency_key"] for record in records}
    assert keys == {"idem-1"}
    checksums = {record["checksum"] for record in records}
    assert len(checksums) == 1
    monkeypatch.delenv("DUAL_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("SCORED_TOPIC_VERSION", raising=False)
    monkeypatch.delenv("SCORED_TOPIC_NEXT_VERSION", raising=False)
    get_settings.cache_clear()
    set_migration_service(None)

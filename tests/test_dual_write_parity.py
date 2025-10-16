from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.leadership import LeaderElector
from app.services.migration import MigrationService, MigrationPhase, set_migration_service
from app.services.parity import ParityService, ParityTracker
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

def test_dual_write_parity(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DUAL_WRITE_ENABLED", "1")
    monkeypatch.setenv("SCORED_TOPIC_VERSION", "1")
    monkeypatch.setenv("SCORED_TOPIC_NEXT_VERSION", "2")
    get_settings.cache_clear()
    parity = ParityService(ParityTracker(window=8))
    state_path = tmp_path / "state.json"
    leader = LeaderElector(role="migration", client=FakeRedis(), ttl_seconds=1.0)
    migration = MigrationService(state_path=state_path, parity_service=parity, leader=leader)
    set_migration_service(migration)

    migration.begin_dual_write("actor-a")

    for idx in range(4):
        payload = {
            "event_id": f"evt-{idx}",
            "transaction_id": f"txn-{idx}",
            "customer_id": "cust",
            "merchant_id": "m",
            "amount": idx + 1,
        }
        records = build_dual_write_records(payload)
        assert len(records) == 2

    metrics = migration.status()["parity"]
    assert pytest.approx(metrics["match_rate"], rel=1e-6) == 1.0

    # Introduce a mismatch for coverage.
    payload = {
        "event_id": "evt-mismatch",
        "transaction_id": "txn-mismatch",
        "customer_id": "cust",
        "merchant_id": "m",
        "amount": 123,
    }
    records = build_dual_write_records(payload)
    # mutate candidate payload to simulate divergence
    records[-1]["payload"]["amount"] = 456
    parity.record("evt-mismatch", records[-1]["version"], records[-1]["payload"])
    metrics = migration.status()["parity"]
    assert metrics["mismatches"] >= 1
    monkeypatch.delenv("DUAL_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("SCORED_TOPIC_VERSION", raising=False)
    monkeypatch.delenv("SCORED_TOPIC_NEXT_VERSION", raising=False)
    get_settings.cache_clear()


def test_state_file_written(tmp_path: Path) -> None:
    state_path = tmp_path / "migration_state.json"
    leader = LeaderElector(role="migration", client=FakeRedis(), ttl_seconds=1.0)
    migration = MigrationService(state_path=state_path, leader=leader)
    set_migration_service(migration)
    migration.begin_dual_write("actor-a")
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert data["phase"] == MigrationPhase.DUAL_WRITE.value

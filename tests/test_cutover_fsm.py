from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.core.leadership import LeaderElector, LeadershipError
from app.services.migration import MigrationPhase, MigrationService


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


def test_cutover_requires_leader(tmp_path: Path) -> None:
    fake = FakeRedis()
    leader = LeaderElector(role="migration", client=fake, ttl_seconds=1.0)
    service = MigrationService(state_path=tmp_path / "state.json", leader=leader)
    service.begin_dual_write("actor-1")
    service.begin_backfill("actor-1")
    service.mark_validate("actor-1")

    with pytest.raises(LeadershipError):
        service.commit_cutover("actor-2")

    service.commit_cutover("actor-1")
    assert service.status()["phase"] == MigrationPhase.MONITOR.value
    service.rollback("actor-1")
    assert service.status()["phase"] == MigrationPhase.DUAL_WRITE.value


def test_leader_reacquire(tmp_path: Path) -> None:
    fake = FakeRedis()
    leader = LeaderElector(role="migration", client=fake, ttl_seconds=0.01)
    service = MigrationService(state_path=tmp_path / "state.json", leader=leader)
    service.begin_dual_write("actor-1")
    time.sleep(0.02)
    # After TTL expiry another actor may grab leadership
    with pytest.raises(LeadershipError):
        service.begin_backfill("actor-2")
    # Original actor can continue via heartbeat
    service.begin_backfill("actor-1")

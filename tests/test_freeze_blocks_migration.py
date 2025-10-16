from __future__ import annotations

from pathlib import Path

import pytest

from app.core.freeze import HTTPException
from app.core.leadership import LeaderElector
from app.services.migration import MigrationService


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


@pytest.mark.parametrize("env_value", ["1", "true", "TRUE"])
def test_freeze_blocks_transitions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env_value: str) -> None:
    monkeypatch.setenv("MAINTENANCE_FREEZE", env_value)
    leader = LeaderElector(role="migration", client=FakeRedis(), ttl_seconds=1.0)
    service = MigrationService(state_path=tmp_path / "state.json", leader=leader)
    with pytest.raises(HTTPException):
        service.begin_dual_write("actor")
    monkeypatch.delenv("MAINTENANCE_FREEZE")
    leader = LeaderElector(role="migration", client=FakeRedis(), ttl_seconds=1.0)
    service = MigrationService(state_path=tmp_path / "state2.json", leader=leader)
    service.begin_dual_write("actor")
    assert service.status()["phase"] == "dual_write"

from __future__ import annotations

from pathlib import Path

from app.core.durability import DurabilityManager


def test_durability_roundtrip(tmp_path: Path) -> None:
    manager = DurabilityManager(base_path=tmp_path)
    manager.append("model", {"step": 1})
    manager.append("model", {"step": 2})
    records = manager.replay("model")
    assert [record.payload for record in records] == [{"step": 1}, {"step": 2}]
    applied: list[int] = []
    manager.recover("model", lambda payload: applied.append(payload["step"]))
    assert applied == [1, 2]

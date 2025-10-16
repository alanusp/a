from __future__ import annotations

from pathlib import Path

import pytest

from app.core.disk_guard import DiskGuard, DiskGuardError


def test_disk_guard_soft_limit(tmp_path: Path, monkeypatch) -> None:
    guard = DiskGuard(base_path=tmp_path)
    guard.soft_threshold = 1.5  # force soft limit breach
    with pytest.raises(DiskGuardError):  # type: ignore[name-defined]
        guard.ensure_capacity(bytes_needed=10, essential=False)


def test_disk_guard_compaction(tmp_path: Path, monkeypatch) -> None:
    guard = DiskGuard(base_path=tmp_path)
    guard.hard_threshold = 0.0
    log = tmp_path / "wal.log"
    log.write_text("line1\n", encoding="utf-8")
    guard.safe_append(log, "line2\n", essential=True, compactor=lambda: None)
    assert "line2" in log.read_text(encoding="utf-8")

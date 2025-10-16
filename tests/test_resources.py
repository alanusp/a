from __future__ import annotations

from pathlib import Path

from app.core.resources import ResourceSnapshot, capture_snapshot


def test_capture_snapshot_reads_cgroup(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "cpu.max").write_text("20000 100000", encoding="utf-8")
    (tmp_path / "cpu.stat").write_text("usage_usec 5000\n", encoding="utf-8")
    (tmp_path / "memory.current").write_text("1024", encoding="utf-8")
    (tmp_path / "memory.max").write_text("2048", encoding="utf-8")
    snapshot = capture_snapshot(tmp_path)
    assert isinstance(snapshot, ResourceSnapshot)
    assert snapshot.cpu_quota == 0.2
    assert snapshot.memory_limit == 2048

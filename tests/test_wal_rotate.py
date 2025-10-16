from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.core.wal_rotate import WalRotator


def test_wal_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("WAL_DIRECTORY", str(tmp_path / "wal"))
    monkeypatch.setenv("WAL_ROTATE_MAX_BYTES", "10")
    monkeypatch.setenv("WAL_ROTATE_MAX_ARCHIVES", "2")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    rotator = WalRotator()
    channel = "events"
    wal_file = rotator._base_path / f"{channel}.log"  # type: ignore[attr-defined]
    wal_file.parent.mkdir(parents=True, exist_ok=True)
    wal_file.write_text("1234567890", encoding="utf-8")

    rotator.maybe_rotate(channel)
    manifest = rotator._manifest  # type: ignore[attr-defined]
    assert channel in manifest
    assert len(manifest[channel]) == 1
    archive_path = Path(manifest[channel][0])
    assert archive_path.exists()
    assert archive_path.exists()


def test_rotate_all(tmp_path, monkeypatch):
    monkeypatch.setenv("WAL_DIRECTORY", str(tmp_path / "wal"))
    monkeypatch.setenv("WAL_ROTATE_MAX_BYTES", "1")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    rotator = WalRotator()
    wal_file = rotator._base_path / "events.log"  # type: ignore[attr-defined]
    wal_file.parent.mkdir(parents=True, exist_ok=True)
    wal_file.write_text("payload", encoding="utf-8")
    rotator.rotate_all()
    assert wal_file.read_text(encoding="utf-8") == ""

from __future__ import annotations

import gzip
import json
import shutil
import time
from pathlib import Path
from threading import RLock
from typing import Dict, List

from app.core.config import get_settings


class WalRotator:
    """Size/age based WAL rotation with gzip archives."""

    def __init__(self) -> None:
        settings = get_settings()
        self._max_bytes = int(getattr(settings, "wal_rotate_max_bytes", 5_000_000))
        self._max_age_seconds = float(getattr(settings, "wal_rotate_max_age_seconds", 3600.0))
        self._max_archives = int(getattr(settings, "wal_rotate_max_archives", 8))
        self._base_path = settings.base_wal_path
        self._archive_path = self._base_path / "archive"
        self._manifest_path = self._base_path / "manifest.json"
        self._archive_path.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._manifest: Dict[str, List[str]] = {}
        if self._manifest_path.exists():
            try:
                self._manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._manifest = {}

    def _channel_path(self, channel: str) -> Path:
        return self._base_path / f"{channel}.log"

    def _archive_name(self, channel: str) -> Path:
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        return self._archive_path / f"{channel}-{ts}.log.gz"

    def _persist_manifest(self) -> None:
        self._manifest_path.write_text(
            json.dumps(self._manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    def maybe_rotate(self, channel: str) -> None:
        with self._lock:
            path = self._channel_path(channel)
            if not path.exists():
                return
            stat = path.stat()
            age = time.time() - stat.st_mtime
            if stat.st_size < self._max_bytes and age < self._max_age_seconds:
                return
            archive_path = self._archive_name(channel)
            with path.open("rb") as src, gzip.open(archive_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            path.write_text("", encoding="utf-8")
            archives = self._manifest.setdefault(channel, [])
            archives.append(str(archive_path))
            if len(archives) > self._max_archives:
                stale = archives[:-self._max_archives]
                for stale_path in stale:
                    candidate = Path(stale_path)
                    if candidate.exists():
                        candidate.unlink()
                self._manifest[channel] = archives[-self._max_archives :]
            self._persist_manifest()

    def prune_oldest(self) -> None:
        with self._lock:
            for channel, archives in list(self._manifest.items()):
                trimmed: List[str] = []
                for path_str in archives:
                    path = Path(path_str)
                    if path.exists():
                        trimmed.append(path_str)
                self._manifest[channel] = trimmed
            self._persist_manifest()

    def rotate_all(self) -> None:
        with self._lock:
            channels = set(self._manifest.keys())
            for candidate in self._base_path.glob("*.log"):
                channels.add(candidate.stem)
        for channel in sorted(channels):
            self.maybe_rotate(channel)


_ROTATOR: WalRotator | None = None


def get_wal_rotator() -> WalRotator:
    global _ROTATOR
    if _ROTATOR is None:
        _ROTATOR = WalRotator()
    return _ROTATOR

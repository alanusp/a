from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.core.config import get_settings
from app.core.disk_guard import DiskGuardError, get_disk_guard
from app.core.json_canonical import canonicalize
from app.core.wal_rotate import get_wal_rotator
from app.core.snapshot_schema import extract_snapshot, stamp_snapshot


@dataclass(frozen=True)
class WalRecord:
    channel: str
    sequence: int
    payload: Dict[str, object]


class DurabilityManager:
    """Crash-only durability through lightweight write-ahead logging."""

    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        default_path = settings.base_wal_path if hasattr(settings, "base_wal_path") else Path(os.getenv("WAL_DIRECTORY", "artifacts/wal"))
        self.base_path = base_path or default_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.RLock] = {}
        self._sequence: Dict[str, int] = {}
        self._disk_guard = get_disk_guard()

    # ------------------------------------------------------------------ internals
    def _channel_path(self, channel: str) -> Path:
        return self.base_path / f"{channel}.log"

    def _lock(self, channel: str) -> threading.RLock:
        if channel not in self._locks:
            self._locks[channel] = threading.RLock()
        return self._locks[channel]

    # ------------------------------------------------------------------ api
    def append(self, channel: str, payload: Dict[str, object]) -> WalRecord:
        lock = self._lock(channel)
        with lock:
            seq = self._sequence.get(channel, 0) + 1
            self._sequence[channel] = seq
            envelope = stamp_snapshot(channel, payload)
            record = WalRecord(channel=channel, sequence=seq, payload=envelope.payload)
            line = canonicalize(
                {
                    "sequence": seq,
                    "schema_version": envelope.schema_version,
                    "created_at": envelope.created_at,
                    "payload": envelope.payload,
                }
            ) + "\n"
            path = self._channel_path(channel)
            try:
                self._disk_guard.safe_append(
                    path,
                    line,
                    essential=True,
                    compactor=lambda: self._compact(channel),
                )
            except DiskGuardError as exc:
                raise RuntimeError(f"wal append blocked: {exc}") from exc
            get_wal_rotator().maybe_rotate(channel)
            return record

    def truncate(self, channel: str) -> None:
        path = self._channel_path(channel)
        if path.exists():
            path.unlink()
        self._sequence[channel] = 0

    def replay(self, channel: str) -> List[WalRecord]:
        path = self._channel_path(channel)
        if not path.exists():
            return []
        records: List[WalRecord] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                envelope = extract_snapshot(channel, payload)
                records.append(
                    WalRecord(
                        channel=channel,
                        sequence=int(payload["sequence"]),
                        payload=dict(envelope.payload),
                    )
                )
        if records:
            self._sequence[channel] = max(record.sequence for record in records)
        return records

    def _compact(self, channel: str, keep: int = 256) -> None:
        path = self._channel_path(channel)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()[-keep:]
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)

    def recover(self, channel: str, handler: Callable[[Dict[str, object]], None]) -> int:
        count = 0
        for record in self.replay(channel):
            handler(record.payload)
            count += 1
        return count

    def latest(self, channel: str) -> Optional[Dict[str, object]]:
        records = self.replay(channel)
        if not records:
            return None
        return records[-1].payload


_MANAGER: DurabilityManager | None = None


def get_durability_manager() -> DurabilityManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = DurabilityManager()
    return _MANAGER

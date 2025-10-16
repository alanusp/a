"""Leak detection utilities for readiness gating."""
from __future__ import annotations

import gc
import os
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock, Thread
from typing import Dict


@dataclass
class LeakSnapshot:
    timestamp: float
    fd_count: int
    object_count: int


class LeakSentinel:
    def __init__(self, *, window: int = 3, fd_threshold: int = 32, object_threshold: int = 10_000) -> None:
        self.window = window
        self.fd_threshold = fd_threshold
        self.object_threshold = object_threshold
        self._snapshots: list[LeakSnapshot] = []
        self._lock = RLock()
        self._alarm = False
        self._thread: Thread | None = None
        self._running = False
        self._diagnostics_path = Path("artifacts/runtime/leak_sentinel.json")
        self._diagnostics_path.parent.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = Thread(target=self._run, name="leak-sentinel", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        while self._running:
            self.sample()
            time.sleep(1.0)

    def sample(self) -> LeakSnapshot:
        snapshot = LeakSnapshot(
            timestamp=time.time(),
            fd_count=_fd_count(),
            object_count=len(gc.get_objects()),
        )
        with self._lock:
            self._snapshots.append(snapshot)
            if len(self._snapshots) > self.window:
                self._snapshots = self._snapshots[-self.window :]
            self._alarm = self._detect_alarm()
            self._write(snapshot)
        return snapshot

    def _detect_alarm(self) -> bool:
        if len(self._snapshots) < self.window:
            return False
        baseline = self._snapshots[0]
        latest = self._snapshots[-1]
        fd_growth = latest.fd_count - baseline.fd_count
        object_growth = latest.object_count - baseline.object_count
        return fd_growth >= self.fd_threshold or object_growth >= self.object_threshold

    def _write(self, snapshot: LeakSnapshot) -> None:
        payload: Dict[str, object] = {
            "timestamp": snapshot.timestamp,
            "fd_count": snapshot.fd_count,
            "object_count": snapshot.object_count,
            "alarm": self._alarm,
        }
        self._diagnostics_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def healthy(self) -> bool:
        with self._lock:
            return not self._alarm

    def status(self) -> Dict[str, object]:
        with self._lock:
            latest = self._snapshots[-1] if self._snapshots else None
            return {
                "alarm": self._alarm,
                "latest": {
                    "timestamp": latest.timestamp if latest else None,
                    "fd_count": latest.fd_count if latest else 0,
                    "object_count": latest.object_count if latest else 0,
                },
            }


def _fd_count() -> int:
    try:
        return len(os.listdir("/proc/self/fd"))
    except FileNotFoundError:  # pragma: no cover - non Linux fallback
        return 0


def get_leak_sentinel() -> LeakSentinel:
    global _SENTINEL
    if _SENTINEL is None:
        _SENTINEL = LeakSentinel()
    return _SENTINEL


_SENTINEL: LeakSentinel | None = None


import json  # placed at end to avoid import cycles for gc tracing

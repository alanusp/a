from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.runtime_state import clear_read_only, set_read_only
from app.core.shutdown import get_shutdown_coordinator


class DrainPhase(str, Enum):
    ACCEPTING = "accepting"
    THROTTLING = "throttling"
    CLOSED = "closed"


@dataclass
class DrainStatus:
    state: str
    reason: Optional[str]
    started_at: Optional[float]
    phase: DrainPhase
    seconds_since: float


class DrainManager:
    """Manages rolling-drain transitions for graceful restarts."""

    def __init__(self) -> None:
        settings = get_settings()
        self._accept_seconds = float(getattr(settings, "drain_accept_seconds", 3.0))
        self._throttle_seconds = float(getattr(settings, "drain_throttle_seconds", 7.0))
        self._lock = threading.RLock()
        self._state = "open"
        self._reason: Optional[str] = None
        self._started_at: Optional[float] = None
        self._status_path = Path("artifacts/runtime/drain_status.json")
        self._status_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers
    def _phase_for_elapsed(self, elapsed: float) -> DrainPhase:
        if elapsed < self._accept_seconds:
            return DrainPhase.ACCEPTING
        if elapsed < self._accept_seconds + self._throttle_seconds:
            return DrainPhase.THROTTLING
        return DrainPhase.CLOSED

    def _update_status(self) -> None:
        payload = self.status()
        self._status_path.write_text(
            json.dumps(
                {
                    "state": payload.state,
                    "reason": payload.reason,
                    "started_at": payload.started_at,
                    "phase": payload.phase.value,
                    "seconds_since": payload.seconds_since,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ public api
    def start(self, reason: str | None = None) -> DrainStatus:
        with self._lock:
            now = time.monotonic()
            self._state = "draining"
            self._reason = reason or "rolling_restart"
            self._started_at = now
            clear_read_only("drain")
            self._update_status()
            coordinator = get_shutdown_coordinator()
            coordinator.flush_all(max(1.0, getattr(get_settings(), "shutdown_flush_timeout", 5.0) / 2))
            return self.status()

    def stop(self) -> DrainStatus:
        with self._lock:
            self._state = "open"
            self._reason = None
            self._started_at = None
            clear_read_only("drain")
            self._update_status()
            return self.status()

    def status(self) -> DrainStatus:
        with self._lock:
            now = time.monotonic()
            if self._started_at is None:
                seconds_since = 0.0
                phase = DrainPhase.ACCEPTING
            else:
                seconds_since = max(0.0, now - self._started_at)
                phase = self._phase_for_elapsed(seconds_since)
            if self._state == "open":
                phase = DrainPhase.ACCEPTING
                seconds_since = 0.0
            elif self._state == "draining" and phase is DrainPhase.CLOSED:
                set_read_only("drain")
                self._state = "readonly"
            elif self._state == "readonly":
                phase = DrainPhase.CLOSED
            return DrainStatus(
                state=self._state,
                reason=self._reason,
                started_at=self._started_at,
                phase=phase,
                seconds_since=seconds_since,
            )

    def should_soft_throttle(self) -> bool:
        status = self.status()
        return status.state in {"draining", "readonly"} and status.phase is DrainPhase.THROTTLING

    def should_block(self) -> bool:
        status = self.status()
        return status.state in {"readonly"}

    def reason(self) -> Optional[str]:
        return self.status().reason


_MANAGER: DrainManager | None = None


def get_drain_manager() -> DrainManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = DrainManager()
    return _MANAGER

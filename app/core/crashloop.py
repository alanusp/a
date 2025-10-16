from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Optional

from app.core.config import get_settings
from app.core.runtime_state import clear_read_only, set_read_only, set_safe_mode


@dataclass
class CrashloopState:
    recent_starts: list[float]
    tripped: bool
    reason: Optional[str]


class CrashloopBreaker:
    def __init__(self) -> None:
        settings = get_settings()
        self._lock = RLock()
        self._window_seconds = float(getattr(settings, "crashloop_window_seconds", 300.0))
        self._max_restarts = int(getattr(settings, "crashloop_max_restarts", 3))
        self._path = Path(getattr(settings, "crashloop_state_path", "artifacts/runtime/crashloop.json"))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                self._state = CrashloopState(
                    recent_starts=list(payload.get("recent_starts", [])),
                    tripped=bool(payload.get("tripped", False)),
                    reason=payload.get("reason"),
                )
            except json.JSONDecodeError:
                self._state = CrashloopState(recent_starts=[], tripped=False, reason=None)
        else:
            self._state = CrashloopState(recent_starts=[], tripped=False, reason=None)

    def record_boot(self) -> CrashloopState:
        with self._lock:
            now = time.time()
            window_start = now - self._window_seconds
            recent = [ts for ts in self._state.recent_starts if ts >= window_start]
            recent.append(now)
            tripped = self._state.tripped
            reason = self._state.reason
            if len(recent) > self._max_restarts:
                tripped = True
                reason = "crashloop"
                set_read_only("crashloop")
                set_safe_mode(True, reason=reason)
            self._state = CrashloopState(recent_starts=recent, tripped=tripped, reason=reason)
            self._persist()
            return self._state

    def acknowledge(self) -> CrashloopState:
        with self._lock:
            self._state.tripped = False
            self._state.reason = None
            self._persist()
            set_safe_mode(False)
            clear_read_only("crashloop")
            return self._state

    def tripped(self) -> bool:
        with self._lock:
            return self._state.tripped

    def state(self) -> CrashloopState:
        with self._lock:
            return CrashloopState(
                recent_starts=list(self._state.recent_starts),
                tripped=self._state.tripped,
                reason=self._state.reason,
            )

    def _persist(self) -> None:
        payload = {
            "recent_starts": self._state.recent_starts,
            "tripped": self._state.tripped,
            "reason": self._state.reason,
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


_BREAKER: CrashloopBreaker | None = None


def get_crashloop_breaker() -> CrashloopBreaker:
    global _BREAKER
    if _BREAKER is None:
        _BREAKER = CrashloopBreaker()
    return _BREAKER

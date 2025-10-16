from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Dict


@dataclass
class _AttemptState:
    attempts: int
    first_seen: float
    locked_until: float


class AdminGuard:
    """Simple token-bucket guard for administrative endpoints."""

    def __init__(
        self,
        *,
        window_seconds: float = 60.0,
        max_attempts: int = 8,
        lockout_seconds: float = 300.0,
    ) -> None:
        self._window = window_seconds
        self._max_attempts = max_attempts
        self._lockout = lockout_seconds
        self._state: Dict[str, _AttemptState] = {}
        self._lock = RLock()

    def record(self, identifier: str, *, success: bool) -> None:
        now = time.monotonic()
        with self._lock:
            state = self._state.get(identifier)
            if state is None:
                state = _AttemptState(attempts=0, first_seen=now, locked_until=0.0)
                self._state[identifier] = state
            if now < state.locked_until:
                raise PermissionError("admin access locked")
            if now - state.first_seen > self._window:
                state.attempts = 0
                state.first_seen = now
            if success:
                state.attempts = 0
                state.first_seen = now
                state.locked_until = 0.0
                return
            state.attempts += 1
            if state.attempts >= self._max_attempts:
                state.locked_until = now + self._lockout
                raise PermissionError("admin lockout engaged")


_GUARD: AdminGuard | None = None


def get_admin_guard() -> AdminGuard:
    global _GUARD
    if _GUARD is None:
        _GUARD = AdminGuard()
    return _GUARD

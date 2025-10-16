from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Optional


@dataclass
class _RuntimeState:
    read_only_reason: Optional[str] = None
    safe_mode_reason: Optional[str] = None
    stale_model: bool = False


_STATE = _RuntimeState()
_LOCK = RLock()


def set_read_only(reason: str) -> None:
    with _LOCK:
        _STATE.read_only_reason = reason or "unspecified"


def clear_read_only(reason: str | None = None) -> None:
    with _LOCK:
        if reason is None or _STATE.read_only_reason == reason:
            _STATE.read_only_reason = None


def read_only_reason() -> Optional[str]:
    with _LOCK:
        return _STATE.read_only_reason


def set_safe_mode(enabled: bool, *, reason: Optional[str] = None) -> None:
    with _LOCK:
        if enabled:
            _STATE.safe_mode_reason = reason or "unspecified"
        else:
            _STATE.safe_mode_reason = None


def safe_mode_reason() -> Optional[str]:
    with _LOCK:
        return _STATE.safe_mode_reason


def set_stale_model(stale: bool) -> None:
    with _LOCK:
        _STATE.stale_model = stale
        if stale:
            if _STATE.safe_mode_reason is None:
                _STATE.safe_mode_reason = "stale_model"
        else:
            if _STATE.safe_mode_reason == "stale_model":
                _STATE.safe_mode_reason = None


def is_stale_model() -> bool:
    with _LOCK:
        return _STATE.stale_model


def is_read_only() -> tuple[bool, Optional[str]]:
    with _LOCK:
        return (_STATE.read_only_reason is not None, _STATE.read_only_reason)


def is_safe_mode() -> bool:
    with _LOCK:
        return _STATE.safe_mode_reason is not None


def snapshot() -> dict[str, Optional[str] | bool]:
    with _LOCK:
        return {
            "read_only_reason": _STATE.read_only_reason,
            "safe_mode_reason": _STATE.safe_mode_reason,
            "stale_model": _STATE.stale_model,
        }

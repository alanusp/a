from __future__ import annotations

import json
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Any, Callable, Dict

from app.core.audit import get_ledger
from app.core.config import Settings, get_settings
from app.core.config_invariants import validate_config_invariants
from app.core.env_invariants import enforce_environment_invariants
from app.core.fs_perms import enforce_filesystem_permissions
from app.core.wal_rotate import get_wal_rotator
from app.core.versioning import verify_artifacts

LOGGER = logging.getLogger("reload")

_Callback = Callable[[], None]


def _snapshot(settings: Settings) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    for key, value in vars(settings).items():
        if isinstance(value, Path):
            snapshot[key] = str(value)
        else:
            snapshot[key] = value
    return snapshot


def _diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    changed: Dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = {"before": before.get(key), "after": after.get(key)}
    return changed


class ReloadManager:
    """Co-ordinate hot reloads triggered via SIGHUP or CLI."""

    def __init__(self) -> None:
        self._callbacks: list[_Callback] = []
        self._lock = threading.RLock()
        self._installed = False

    def register(self, callback: _Callback) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def install_signal_handler(self) -> None:
        with self._lock:
            if self._installed:
                return
            signal.signal(signal.SIGHUP, self._handle_signal)
            self._installed = True

    def _handle_signal(self, signum: int, frame: object | None) -> None:  # pragma: no cover - signal entry
        try:
            LOGGER.info("received SIGHUP; reloading configuration")
            self.reload()
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("reload failed: %s", exc)

    def reload(self, *, dry_run: bool = False) -> Dict[str, Any]:
        with self._lock:
            before_settings = get_settings()
            before = _snapshot(before_settings)
            if dry_run:
                preview = {"changed": _diff(before, before)}
            else:
                get_settings.cache_clear()
                enforce_environment_invariants()
                enforce_filesystem_permissions()
                verify_artifacts()
                validate_config_invariants()
                after_settings = get_settings()
                after = _snapshot(after_settings)
                changed = _diff(before, after)
                get_wal_rotator().rotate_all()
                for callback in self._callbacks:
                    callback()
                ledger = get_ledger()
                ledger.append(
                    event_id=f"reload:{os.getpid()}:{signal.SIGHUP}",
                    payload={
                        "kind": "reload",
                        "dry_run": False,
                        "changed": changed,
                    },
                )
                preview = {"changed": changed}
        return preview


_MANAGER: ReloadManager | None = None


def get_reload_manager() -> ReloadManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ReloadManager()
    return _MANAGER


def install_reload_handler() -> None:
    get_reload_manager().install_signal_handler()


if __name__ == "__main__":
    dry_run = os.getenv("RELOAD_DRY_RUN", "0").lower() in {"1", "true", "yes"}
    result = get_reload_manager().reload(dry_run=dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))

from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path
from typing import Callable, List, Tuple

from app.core.config import get_settings
from app.core.diagnostics import build_bundle
from app.core.thread_dump import write_thread_dump

LOGGER = logging.getLogger(__name__)

FlushCallback = Callable[[float], None]
DiagCallback = Callable[[], Path | None]


class ShutdownCoordinator:
    def __init__(self) -> None:
        self._callbacks: List[Tuple[str, FlushCallback]] = []
        self._diag: DiagCallback | None = lambda: build_bundle(None)
        self._installed = False
        self._lock = threading.Lock()
        self._settings = get_settings()

    def register(self, name: str, callback: FlushCallback) -> None:
        with self._lock:
            self._callbacks.append((name, callback))

    def register_diag(self, callback: DiagCallback) -> None:
        with self._lock:
            self._diag = callback

    def install(self) -> None:
        if self._installed:
            return
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_shutdown)
        if hasattr(signal, "SIGUSR1"):
            signal.signal(signal.SIGUSR1, self._handle_diag)
        if hasattr(signal, "SIGUSR2"):
            signal.signal(signal.SIGUSR2, self._handle_thread_dump)
        self._installed = True

    def _handle_shutdown(self, signum, frame) -> None:  # type: ignore[override]
        deadline = time.monotonic() + float(getattr(self._settings, "shutdown_flush_timeout", 5.0))
        LOGGER.info("shutdown signal received", extra={"signal": signum})
        for name, callback in list(self._callbacks):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                LOGGER.warning("shutdown budget exhausted", extra={"callback": name})
                break
            try:
                callback(max(0.1, remaining))
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("shutdown callback failed", extra={"callback": name})
        raise SystemExit(0)

    def _handle_diag(self, signum, frame) -> None:  # type: ignore[override]
        diag = None
        with self._lock:
            if self._diag is not None:
                try:
                    diag = self._diag()
                except Exception:  # pragma: no cover - defensive logging
                    LOGGER.exception("diagnostic bundle generation failed")
        if diag is not None:
            LOGGER.info("diagnostic bundle created", extra={"path": str(diag)})

    def _handle_thread_dump(self, signum, frame) -> None:  # type: ignore[override]
        try:
            path = write_thread_dump()
            LOGGER.info("thread dump captured", extra={"path": str(path)})
        except Exception:  # pragma: no cover - defensive
            LOGGER.exception("thread dump failed")

    def flush_all(self, budget: float | None = None) -> list[tuple[str, bool]]:
        """Flush registered callbacks outside of signal handling.

        Returns a list of (name, success) tuples.
        """

        deadline = time.monotonic() + (budget or float(getattr(self._settings, "shutdown_flush_timeout", 5.0)))
        results: list[tuple[str, bool]] = []
        for name, callback in list(self._callbacks):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                results.append((name, False))
                continue
            try:
                callback(max(0.1, remaining))
                results.append((name, True))
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("flush callback failed", extra={"callback": name})
                results.append((name, False))
        return results


_COORDINATOR = ShutdownCoordinator()


def get_shutdown_coordinator() -> ShutdownCoordinator:
    return _COORDINATOR

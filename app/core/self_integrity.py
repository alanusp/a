from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.json_canonical import canonicalize
from app.core.runtime_state import clear_read_only, set_read_only
from app.core.versioning import VersionMismatchError, verify_artifacts


class IntegrityMonitor:
    """Continuously validates code and artifact hashes against the manifest."""

    def __init__(
        self,
        *,
        manifest_path: Path | None = None,
        status_path: Path | None = None,
        interval_seconds: int = 3600,
    ) -> None:
        self.manifest_path = manifest_path or Path("artifacts/version_manifest.json")
        self.status_path = status_path or Path("artifacts/integrity_status.json")
        self.interval_seconds = max(60, interval_seconds)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    def verify_once(self) -> bool:
        with self._lock:
            try:
                verify_artifacts(self.manifest_path)
            except VersionMismatchError as exc:
                self._last_error = str(exc)
                self._write_status(ok=False, detail=str(exc))
                set_read_only("integrity_mismatch")
                return False
            else:
                self._last_error = None
                self._write_status(ok=True, detail="")
                clear_read_only("integrity_mismatch")
                return True

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="integrity-monitor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def status(self) -> dict[str, Optional[str]]:
        with self._lock:
            return {"ok": self._last_error is None, "error": self._last_error}

    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.verify_once()

    def _write_status(self, *, ok: bool, detail: str) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": ok,
            "detail": detail,
        }
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(canonicalize(payload), encoding="utf-8")


_MONITOR: IntegrityMonitor | None = None


def get_integrity_monitor() -> IntegrityMonitor:
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = IntegrityMonitor()
    return _MONITOR

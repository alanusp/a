from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.runtime_state import set_safe_mode, set_stale_model


class ModelStalenessMonitor:
    def __init__(self, *, model_path: Optional[Path] = None, calibrator_path: Optional[Path] = None) -> None:
        settings = get_settings()
        self.model_path = model_path or settings.model_path
        self.calibration_path = calibrator_path or settings.calibration_path
        self.max_age_seconds = int(os.getenv("MAX_MODEL_AGE_SECONDS", "86400"))
        self._last_check: datetime | None = None
        self._stale: bool = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _age_seconds(self, path: Path) -> float:
        if not path.exists():
            return float("inf")
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return (datetime.now(timezone.utc) - mtime).total_seconds()

    def evaluate(self) -> bool:
        age_model = self._age_seconds(self.model_path)
        age_cal = self._age_seconds(self.calibration_path)
        stale = age_model > self.max_age_seconds or age_cal > self.max_age_seconds
        self._stale = stale
        set_stale_model(stale)
        if stale:
            set_safe_mode(True, reason="stale_model")
        else:
            set_safe_mode(False)
        self._last_check = datetime.now(timezone.utc)
        return not stale

    def stale(self) -> bool:
        return self._stale

    def start(self, interval_seconds: int = 300) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="model-staleness-monitor",
            daemon=True,
            args=(max(60, interval_seconds),),
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self, interval: int) -> None:
        while not self._stop.wait(interval):
            self.evaluate()


_MONITOR: ModelStalenessMonitor | None = None


def get_staleness_monitor() -> ModelStalenessMonitor:
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = ModelStalenessMonitor()
    return _MONITOR

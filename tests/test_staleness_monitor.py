from __future__ import annotations

import os
import time
from pathlib import Path

from app.core.runtime_state import is_safe_mode, set_safe_mode
from app.core.staleness import ModelStalenessMonitor


def test_staleness_monitor_triggers(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "model.bin"
    model.write_text("weights", encoding="utf-8")
    cal = tmp_path / "cal.json"
    cal.write_text("cal", encoding="utf-8")

    monitor = ModelStalenessMonitor(model_path=model, calibrator_path=cal)
    monitor.max_age_seconds = 1
    assert monitor.evaluate() is True
    # simulate staleness
    old = time.time() - 3600
    os.utime(model, (old, old))
    os.utime(cal, (old, old))
    assert monitor.evaluate() is False
    assert is_safe_mode() is True
    set_safe_mode(False)

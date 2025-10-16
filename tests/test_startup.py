from __future__ import annotations

from app.core.config import get_settings
from app.core.startup import get_startup_state, reset_startup_state, warm_startup


def setup_module(_: object) -> None:
    get_settings.cache_clear()
    reset_startup_state()


def test_startup_warm_ready() -> None:
    state = warm_startup(force=True)
    assert state.startup_time_ms >= 0.0
    assert get_startup_state().ready == state.ready


def test_startup_respects_budget(monkeypatch) -> None:
    monkeypatch.setenv("COLD_START_BUDGET_MS", "0")
    get_settings.cache_clear()
    reset_startup_state()
    state = warm_startup(force=True)
    assert not state.ready
    assert state.error
    monkeypatch.delenv("COLD_START_BUDGET_MS", raising=False)
    get_settings.cache_clear()
    reset_startup_state()

from __future__ import annotations

import pytest

from app.core import drain as drain_module
from app.core import crashloop as crashloop_module
from app.core.config import get_settings
from app.core.runtime_state import clear_read_only, set_safe_mode


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("WAL_DIRECTORY", "artifacts/wal-test")
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]
    drain_module._MANAGER = None
    crashloop_module._BREAKER = None
    clear_read_only("drain")
    set_safe_mode(False)


def test_drain_transitions(monkeypatch):
    monkeypatch.setenv("DRAIN_ACCEPT_SECONDS", "0.05")
    monkeypatch.setenv("DRAIN_THROTTLE_SECONDS", "0.1")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    drain_module._MANAGER = None
    manager = drain_module.get_drain_manager()

    start_time = 100.0
    monkeypatch.setattr(drain_module.time, "monotonic", lambda: start_time)
    status = manager.start("rolling")
    assert status.state == "draining"
    assert status.phase.value == "accepting"

    monkeypatch.setattr(drain_module.time, "monotonic", lambda: start_time + 0.06)
    mid_status = manager.status()
    assert mid_status.phase.value == "throttling"
    assert manager.should_soft_throttle()

    monkeypatch.setattr(drain_module.time, "monotonic", lambda: start_time + 1.0)
    assert manager.should_block()
    status = manager.status()
    assert status.state == "readonly"

    manager.stop()
    assert not manager.should_block()


def test_crashloop_breaker(monkeypatch, tmp_path):
    monkeypatch.setenv("CRASHLOOP_MAX_RESTARTS", "2")
    monkeypatch.setenv("CRASHLOOP_WINDOW_SECONDS", "60")
    monkeypatch.setenv("CRASHLOOP_STATE_PATH", str(tmp_path / "state.json"))
    get_settings.cache_clear()  # type: ignore[attr-defined]
    crashloop_module._BREAKER = None
    breaker = crashloop_module.get_crashloop_breaker()

    now = 1_000.0
    times = iter([now, now + 10, now + 20])
    monkeypatch.setattr(crashloop_module.time, "time", lambda: next(times))

    breaker.record_boot()
    breaker.record_boot()
    state = breaker.record_boot()
    assert state.tripped is True
    assert state.reason == "crashloop"

    breaker.acknowledge()
    assert not breaker.state().tripped

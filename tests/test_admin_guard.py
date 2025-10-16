from __future__ import annotations

import pytest

from app.core.admin_guard import AdminGuard


def test_admin_guard_lockout_and_reset(monkeypatch):
    guard = AdminGuard(window_seconds=1.0, max_attempts=2, lockout_seconds=1.0)
    guard.record("tenant", success=False)
    with pytest.raises(PermissionError):
        guard.record("tenant", success=False)
    with pytest.raises(PermissionError):
        guard.record("tenant", success=True)
    # simulate time passing by monkeypatching time.monotonic
    original = guard._state["tenant"].locked_until  # type: ignore[attr-defined]
    monkeypatch.setattr("app.core.admin_guard.time.monotonic", lambda: original + 2)
    guard.record("tenant", success=True)

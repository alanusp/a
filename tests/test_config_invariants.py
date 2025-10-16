from __future__ import annotations

import os

import pytest

from app.core.config import get_settings
from app.core.config_invariants import ConfigInvariantError, validate_config_invariants


def test_config_invariants_freeze_blocks_dual_write(monkeypatch) -> None:
    monkeypatch.setenv("MAINTENANCE_FREEZE", "1")
    monkeypatch.setenv("DUAL_WRITE_ENABLED", "1")
    get_settings.cache_clear()
    with pytest.raises(ConfigInvariantError):
        validate_config_invariants()


def test_config_invariants_safe_mode(monkeypatch) -> None:
    monkeypatch.delenv("MAINTENANCE_FREEZE", raising=False)
    monkeypatch.setenv("TRAFFIC_SAFE_MODE", "1")
    monkeypatch.setenv("ONLINE_UPDATES_ENABLED", "1")
    get_settings.cache_clear()
    with pytest.raises(ConfigInvariantError):
        validate_config_invariants()

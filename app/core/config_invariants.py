from __future__ import annotations

import os
from typing import List

from app.core.config import get_settings
from app.core.freeze import freeze_status
from app.core.flags import get_feature_flags


class ConfigInvariantError(RuntimeError):
    pass


def validate_config_invariants() -> None:
    settings = get_settings()
    flags = get_feature_flags()
    errors: List[str] = []

    if freeze_status().enabled and settings.dual_write_enabled:
        errors.append("maintenance freeze cannot run with dual-write enabled")

    safe_mode_flag = os.getenv("TRAFFIC_SAFE_MODE", "0").lower() in {"1", "true", "yes"}
    if (flags.enabled("traffic.safe_mode") or safe_mode_flag) and settings.online_updates_enabled:
        errors.append("safe mode requires online updates disabled")

    if os.getenv("MAINTENANCE_FREEZE", "0").lower() in {"1", "true", "yes"} and os.getenv(
        "ALLOW_CONFIG_CHANGES", "0"
    ).lower() not in {"1", "true", "yes"}:
        # ensure migrations are not attempted during freeze
        if os.getenv("DUAL_WRITE_ENABLED", "0").lower() in {"1", "true", "yes"}:
            errors.append("freeze blocks dual write transitions")

    if errors:
        raise ConfigInvariantError("; ".join(errors))

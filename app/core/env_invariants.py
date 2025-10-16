from __future__ import annotations

import os
from dataclasses import dataclass

EXPECTED_LOCALE = "C.UTF-8"
EXPECTED_TZ = "UTC"
EXPECTED_UMASK = 0o27


@dataclass(frozen=True)
class EnvironmentSnapshot:
    locale: str
    timezone: str
    umask: int


class EnvironmentInvariantError(RuntimeError):
    pass


def _current_umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


def enforce_environment_invariants() -> EnvironmentSnapshot:
    locale = os.environ.setdefault("LC_ALL", EXPECTED_LOCALE)
    if locale != EXPECTED_LOCALE:
        raise EnvironmentInvariantError(f"LC_ALL must be {EXPECTED_LOCALE}, found {locale}")
    timezone = os.environ.setdefault("TZ", EXPECTED_TZ)
    if timezone != EXPECTED_TZ:
        raise EnvironmentInvariantError(f"TZ must be {EXPECTED_TZ}, found {timezone}")
    os.environ.setdefault("LC_CTYPE", EXPECTED_LOCALE)
    current_umask = _current_umask()
    if current_umask != EXPECTED_UMASK:
        os.umask(EXPECTED_UMASK)
        current_umask = _current_umask()
        if current_umask != EXPECTED_UMASK:
            raise EnvironmentInvariantError(
                f"unable to set umask to {oct(EXPECTED_UMASK)} (current {oct(current_umask)})"
            )
    return EnvironmentSnapshot(locale=locale, timezone=timezone, umask=current_umask)

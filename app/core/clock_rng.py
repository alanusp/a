"""Deterministic clock and RNG façade for runtime and tests."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class ClockFacade:
    _now: Callable[[], int]

    def now_ns(self) -> int:
        return self._now()


@dataclass
class RngFacade:
    _token_bytes: Callable[[int], bytes]

    def token_bytes(self, nbytes: int) -> bytes:
        return self._token_bytes(nbytes)


_DEFAULT_CLOCK = ClockFacade(time.monotonic_ns)
_DEFAULT_RNG = RngFacade(secrets.token_bytes)


def get_clock() -> ClockFacade:
    return _DEFAULT_CLOCK


def get_rng() -> RngFacade:
    return _DEFAULT_RNG


def install_test_clock(now: Callable[[], int]) -> None:
    global _DEFAULT_CLOCK
    _DEFAULT_CLOCK = ClockFacade(now)


def install_test_rng(factory: Callable[[int], bytes]) -> None:
    global _DEFAULT_RNG
    _DEFAULT_RNG = RngFacade(factory)


def reset_clock_rng() -> None:
    global _DEFAULT_CLOCK, _DEFAULT_RNG
    _DEFAULT_CLOCK = ClockFacade(time.monotonic_ns)
    _DEFAULT_RNG = RngFacade(secrets.token_bytes)

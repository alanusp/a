"""Utilities for reducing timing side channels on sensitive comparisons."""
from __future__ import annotations

import time
import hmac
from dataclasses import dataclass
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int:  # pragma: no cover - structural typing helper
        """Return the current monotonic time in nanoseconds."""


class Rng(Protocol):
    def token_bytes(self, nbytes: int) -> bytes:  # pragma: no cover - structural typing helper
        """Return cryptographically secure bytes."""


@dataclass
class TimingPad:
    elapsed_ms: float
    sleep_ms: float


def constant_time_compare(left: str, right: str) -> bool:
    left_bytes = left.encode("utf-8")
    right_bytes = right.encode("utf-8")
    return hmac.compare_digest(left_bytes, right_bytes)


def pad_failure(
    *,
    clock: Clock,
    rng: Rng,
    started_ns: int,
    min_duration_ms: float = 25.0,
    jitter_ms: float = 5.0,
) -> TimingPad:
    """Return the sleep duration required to obscure timing differences."""

    now_ns = clock.now_ns()
    elapsed_ms = (now_ns - started_ns) / 1_000_000
    if elapsed_ms < min_duration_ms:
        needed = min_duration_ms - elapsed_ms
        if jitter_ms > 0:
            # Generate a deterministic jitter based on secure randomness.
            rand = int.from_bytes(rng.token_bytes(2), "big")
            jitter = (rand % int(jitter_ms * 1000)) / 1000
        else:
            jitter = 0.0
        sleep_ms = max(0.0, needed + jitter)
    else:
        sleep_ms = 0.0
    return TimingPad(elapsed_ms=elapsed_ms, sleep_ms=sleep_ms)


def sleep_pad(pad: TimingPad) -> None:
    if pad.sleep_ms <= 0:
        return
    time.sleep(pad.sleep_ms / 1000)

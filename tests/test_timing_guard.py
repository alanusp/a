import math

from app.core.clock_rng import get_clock, get_rng, install_test_clock, install_test_rng, reset_clock_rng
from app.core.timing_guard import constant_time_compare, pad_failure


def test_constant_time_compare() -> None:
    assert constant_time_compare("secret", "secret") is True
    assert constant_time_compare("secret", "other") is False


def test_pad_failure_computes_sleep() -> None:
    try:
        install_test_clock(lambda: 1_000_000)
        install_test_rng(lambda n: b"\x00" * n)
        clock = get_clock()
        rng = get_rng()
        pad = pad_failure(clock=clock, rng=rng, started_ns=100_000, min_duration_ms=2.0, jitter_ms=0.0)
        assert math.isclose(pad.sleep_ms, 1.1, rel_tol=0.05)
    finally:
        reset_clock_rng()

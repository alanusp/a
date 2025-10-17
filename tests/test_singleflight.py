from __future__ import annotations

import threading
import time

from app.core.cache import NegativeCache
from app.core.singleflight import SingleFlight


def test_singleflight_deduplicates_concurrent_calls() -> None:
    flight: SingleFlight[int] = SingleFlight(ttl_seconds=1.0)
    counter = 0

    def expensive() -> int:
        nonlocal counter
        time.sleep(0.05)
        counter += 1
        return counter

    results: list[int] = []

    def worker() -> None:
        results.append(flight.run("key", expensive))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert counter == 1
    assert results == [1] * 5


def test_negative_cache_remembers() -> None:
    cache = NegativeCache("test-neg", ttl_seconds=0.5, jitter=0.0, max_size=4)
    assert not cache.contains("missing")
    cache.remember("missing")
    assert cache.contains("missing")
    time.sleep(0.6)
    assert not cache.contains("missing")

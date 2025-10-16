from __future__ import annotations

from app.core.cache import TTLCache


def test_ttl_expiry_under_time_warp(monkeypatch) -> None:
    clock = {"now": 0.0}

    def fake_monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr("app.core.cache.time.monotonic", fake_monotonic)
    cache = TTLCache(name="warp", ttl_seconds=1.0, jitter=0.0, max_size=16)
    cache.set("key", "value")
    found, value = cache.get("key")
    assert found and value == "value"
    clock["now"] = 2.0
    found, _ = cache.get("key")
    assert not found

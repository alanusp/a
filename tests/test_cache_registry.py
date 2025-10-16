from __future__ import annotations

from app.core.cache import TTLCache, get_cache_registry


def test_cache_registry_summary_tracks_metrics() -> None:
    cache = TTLCache("test-cache", ttl_seconds=0.5, jitter=0.0, max_size=8)
    cache.set("alpha", 1)
    found, _ = cache.get("alpha")
    assert found
    summary = get_cache_registry().summary()
    assert "test-cache" in summary
    data = summary["test-cache"]
    assert data["hits"] >= 1
    assert data["size"] >= 1

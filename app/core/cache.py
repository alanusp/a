from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, MutableMapping


@dataclass
class CacheStats:
    name: str
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    sets: int = 0
    negatives: int = 0
    size: int = 0
    max_size: int = 0
    ttl_seconds: float = 0.0


class CacheRegistry:
    def __init__(self) -> None:
        self._caches: Dict[str, "TTLCache"] = {}
        self._lock = threading.Lock()

    def register(self, cache: "TTLCache") -> None:
        with self._lock:
            self._caches[cache.name] = cache

    def summary(self) -> Dict[str, Dict[str, float | int]]:
        with self._lock:
            items = list(self._caches.values())
        return {cache.name: cache.snapshot() for cache in items}

    def caches(self) -> Iterable["TTLCache"]:
        with self._lock:
            return list(self._caches.values())


_REGISTRY = CacheRegistry()


def get_cache_registry() -> CacheRegistry:
    return _REGISTRY


class TTLCache:
    def __init__(
        self,
        name: str,
        *,
        ttl_seconds: float,
        jitter: float = 0.1,
        max_size: int = 512,
    ) -> None:
        self.name = name
        self.ttl_seconds = ttl_seconds
        self.jitter = max(0.0, jitter)
        self.max_size = max_size
        self._data: MutableMapping[Any, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._stats = CacheStats(name=name, max_size=max_size, ttl_seconds=ttl_seconds)
        get_cache_registry().register(self)

    def _expiry(self) -> float:
        base = self.ttl_seconds
        if base <= 0:
            return float("inf")
        jitter = base * self.jitter
        return time.monotonic() + base + random.uniform(-jitter, jitter)

    def _prune(self) -> None:
        if self.max_size <= 0:
            return
        if len(self._data) <= self.max_size:
            return
        # remove oldest entries
        items = sorted(self._data.items(), key=lambda item: item[1][1])
        while len(items) > self.max_size:
            key, _ = items.pop(0)
            self._data.pop(key, None)
            self._stats.evictions += 1
        self._stats.size = len(self._data)

    def get(self, key: Any) -> tuple[bool, Any]:
        with self._lock:
            record = self._data.get(key)
            if not record:
                self._stats.misses += 1
                return False, None
            value, expiry = record
            if expiry < time.monotonic():
                self._data.pop(key, None)
                self._stats.misses += 1
                return False, None
            self._stats.hits += 1
            return True, value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = (value, self._expiry())
            self._stats.sets += 1
            self._stats.size = len(self._data)
            self._prune()

    def invalidate(self, key: Any) -> None:
        with self._lock:
            if key in self._data:
                self._data.pop(key, None)
                self._stats.evictions += 1
                self._stats.size = len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._stats.size = 0

    def snapshot(self) -> Dict[str, float | int]:
        with self._lock:
            return {
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "evictions": self._stats.evictions,
                "sets": self._stats.sets,
                "size": len(self._data),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "negatives": self._stats.negatives,
            }


_NEGATIVE_SENTINEL = object()


class NegativeCache(TTLCache):
    def remember(self, key: Any) -> None:
        super().set(key, _NEGATIVE_SENTINEL)
        with self._lock:
            self._stats.negatives += 1

    def contains(self, key: Any) -> bool:
        found, value = super().get(key)
        return bool(found and value is _NEGATIVE_SENTINEL)

    def set(self, key: Any, value: Any) -> None:  # type: ignore[override]
        raise RuntimeError("use remember() for negative cache")

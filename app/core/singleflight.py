from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Call(Generic[T]):
    condition: threading.Condition
    expiry: float
    result: T | None = None
    error: BaseException | None = None
    done: bool = False


@dataclass
class _AsyncCall(Generic[T]):
    future: asyncio.Future
    expiry: float


class SingleFlight(Generic[T]):
    """Deduplicate concurrent invocations of expensive operations."""

    def __init__(self, ttl_seconds: float = 10.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._calls: Dict[str, _Call[T]] = {}
        self._lock = threading.Lock()
        self._async_calls: Dict[str, _AsyncCall[T]] = {}
        self._async_lock = asyncio.Lock()

    def run(self, key: str, fn: Callable[[], T]) -> T:
        now = time.monotonic()
        with self._lock:
            existing = self._calls.get(key)
            if existing and not existing.done and existing.expiry > now:
                condition = existing.condition
                while not existing.done:
                    condition.wait(timeout=max(existing.expiry - time.monotonic(), 0.1))
                if existing.error is not None:
                    raise existing.error
                assert existing.result is not None
                return existing.result
            if existing and (existing.done or existing.expiry <= now):
                self._calls.pop(key, None)
            condition = threading.Condition(self._lock)
            call = _Call(condition=condition, expiry=now + self.ttl_seconds)
            self._calls[key] = call

        try:
            result = fn()
        except BaseException as exc:  # pragma: no cover - defensive
            with self._lock:
                call = self._calls.get(key)
                if call:
                    call.error = exc
                    call.done = True
                    call.condition.notify_all()
                    self._calls.pop(key, None)
            raise

        with self._lock:
            call = self._calls.get(key)
            if call:
                call.result = result
                call.done = True
                call.condition.notify_all()
                self._calls.pop(key, None)
        return result

    async def run_async(self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        now = time.monotonic()
        async with self._async_lock:
            existing = self._async_calls.get(key)
            if existing and not existing.future.done() and existing.expiry > now:
                return await existing.future
            if existing and (existing.future.done() or existing.expiry <= now):
                self._async_calls.pop(key, None)
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            self._async_calls[key] = _AsyncCall(future=future, expiry=now + self.ttl_seconds)

        try:
            result = await fn()
        except BaseException as exc:  # pragma: no cover - defensive
            future.set_exception(exc)
            async with self._async_lock:
                self._async_calls.pop(key, None)
            raise

        future.set_result(result)
        async with self._async_lock:
            self._async_calls.pop(key, None)
        return result


_GLOBAL_FLIGHT = SingleFlight[Any](ttl_seconds=5.0)


def singleflight_run(key: str, fn: Callable[[], T]) -> T:
    return _GLOBAL_FLIGHT.run(key, fn)


async def singleflight_run_async(key: str, fn: Callable[[], Awaitable[T]]) -> T:
    return await _GLOBAL_FLIGHT.run_async(key, fn)

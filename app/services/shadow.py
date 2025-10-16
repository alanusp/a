from __future__ import annotations

import asyncio
import asyncio
import hashlib
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Mapping, Sequence


@dataclass(slots=True)
class ShadowRecord:
    transaction_id: str
    model_version: str
    probability: float
    latency_ms: float
    captured_at: float
    features: Sequence[float]
    trace_id: str | None = None

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.transaction_id.encode())
        digest.update(self.model_version.encode())
        digest.update(str(round(self.latency_ms, 3)).encode())
        digest.update(str(round(self.probability, 6)).encode())
        return digest.hexdigest()


class ShadowRepository:
    def store(self, record: ShadowRecord) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def latest(self, limit: int = 50) -> list[ShadowRecord]:  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryShadowRepository(ShadowRepository):
    """Thread-safe circular buffer for captured shadow predictions."""

    def __init__(self, maxlen: int = 500) -> None:
        self._records: Deque[ShadowRecord] = deque(maxlen=maxlen)
        self._lock = Lock()

    def store(self, record: ShadowRecord) -> None:
        with self._lock:
            self._records.appendleft(record)

    def latest(self, limit: int = 50) -> list[ShadowRecord]:
        with self._lock:
            return list(list(self._records)[:limit])


class ShadowTrafficService:
    """Mirror live requests to candidate models without impacting caller latency."""

    def __init__(
        self,
        *,
        repository: ShadowRepository | None = None,
        clock: callable | None = None,
    ) -> None:
        self._repository = repository or InMemoryShadowRepository()
        self._clock = clock or time.monotonic

    @staticmethod
    def should_shadow(headers: Mapping[str, str]) -> bool:
        value = headers.get("X-Shadow", "")
        return value.lower() in {"1", "true", "yes"}

    @staticmethod
    def resolve_model_version(headers: Mapping[str, str]) -> str:
        return headers.get("X-Model-Version", "candidate-unknown")

    async def record(
        self,
        *,
        headers: Mapping[str, str],
        transaction_id: str,
        features: Sequence[float],
        probability: float,
        latency_ms: float,
        trace_context: Mapping[str, str] | None = None,
    ) -> None:
        if not self.should_shadow(headers):
            return
        record = ShadowRecord(
            transaction_id=transaction_id,
            model_version=self.resolve_model_version(headers),
            probability=probability,
            latency_ms=latency_ms,
            captured_at=self._clock(),
            features=list(features),
            trace_id=(trace_context or {}).get("trace_id"),
        )
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(self._repository.store, record))

    def summarize(self, window: int = 100) -> dict[str, float]:
        recent = self._repository.latest(window)
        if not recent:
            return {
                "count": 0.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
            }
        latencies = sorted(record.latency_ms for record in recent)
        index = max(int(len(latencies) * 0.95) - 1, 0)
        return {
            "count": float(len(recent)),
            "avg_latency_ms": sum(latencies) / len(latencies),
            "p95_latency_ms": latencies[index],
        }

    def drain(self) -> list[ShadowRecord]:
        items = self._repository.latest(1000)
        return items

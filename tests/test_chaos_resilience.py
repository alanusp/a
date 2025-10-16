from __future__ import annotations

import time

from app.services.shadow import InMemoryShadowRepository, ShadowTrafficService
from streaming.pipeline import BackpressureController, RedisDeduplicator


def test_shadow_service_handles_delayed_store():
    class SlowRepo(InMemoryShadowRepository):
        def store(self, record):  # type: ignore[override]
            time.sleep(0.01)
            super().store(record)

    repo = SlowRepo()
    service = ShadowTrafficService(repository=repo)
    headers = {"X-Shadow": "true"}
    start = time.perf_counter()
    import asyncio

    asyncio.run(
        service.record(
            headers=headers,
            transaction_id="t-1",
            features=[0.1],
            probability=0.5,
            latency_ms=5.0,
        )
    )
    duration = time.perf_counter() - start
    assert duration < 0.05


def test_backpressure_controller_prevents_growth():
    controller = BackpressureController(max_records=3)
    for idx in range(10):
        controller.push({"id": idx})
    drained = controller.drain()
    assert len(drained) <= 3


def test_deduplicator_ttl_allows_reentry():
    deduper = RedisDeduplicator(ttl_seconds=1)
    assert deduper.check_and_record("event", now=time.time()) is True
    assert deduper.check_and_record("event", now=time.time()) is False
    time.sleep(1.1)
    assert deduper.check_and_record("event", now=time.time()) is True

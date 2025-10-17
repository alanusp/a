from __future__ import annotations

from streaming import pipeline


def test_deduplication_blocks_duplicates():
    pipeline._deduper = pipeline.RedisDeduplicator(ttl_seconds=10)
    payload = {
        "transaction_id": "t-1",
        "customer_id": "c-1",
        "merchant_id": "m-1",
        "amount": 10.0,
    }
    payload["event_id"] = pipeline.compose_event_id(payload)
    assert pipeline.deduplicate(payload) is True
    assert pipeline.deduplicate(payload) is False


def test_backpressure_controller_drops_when_full():
    controller = pipeline.BackpressureController(max_records=2)
    assert controller.push({"id": 1}) is True
    assert controller.push({"id": 2}) is True
    assert controller.push({"id": 3}) is False
    assert controller.drain() == [{"id": 1}, {"id": 2}]


def test_drift_metrics_helpers():
    psi = pipeline.compute_psi([0.1, 0.2, 0.3], [0.2, 0.3, 0.4])
    ks = pipeline.compute_ks([0.1, 0.2, 0.3], [0.2, 0.3, 0.4])
    assert psi >= 0.0
    assert 0.0 <= ks <= 1.0

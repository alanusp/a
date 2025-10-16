from __future__ import annotations

import math
import random

from app.services.sketch_book import SketchBook
from sketches.cms import CountMinSketch
from sketches.hll import HyperLogLog
from sketches.stable_bloom import StableBloomFilter


def test_count_min_sketch_error_bound() -> None:
    sketch = CountMinSketch(width=64, depth=4, seeds=[1, 2, 3, 4])
    population = {f"key-{idx}": idx for idx in range(20)}
    for key, count in population.items():
        for _ in range(count):
            sketch.add(key)
    epsilon_bound = sketch.epsilon * sum(population.values())
    for key, true_count in population.items():
        estimate = sketch.estimate(key)
        assert estimate >= true_count
        assert estimate - true_count <= math.ceil(epsilon_bound)


def test_hyperloglog_merge_and_estimate() -> None:
    left = HyperLogLog(precision=6)
    right = HyperLogLog(precision=6)
    for idx in range(500):
        (left if idx % 2 == 0 else right).add(f"user-{idx}")
    merged = HyperLogLog(precision=6)
    merged.merge([left, right])
    assert abs(merged.estimate() - 500) / 500 < 0.2


def test_stable_bloom_filter_bounds() -> None:
    random.seed(42)
    bloom = StableBloomFilter(capacity=256, hash_count=4, decay=1)
    for idx in range(200):
        token = f"txn-{idx}"
        bloom.add(token)
    hits = sum(1 for idx in range(200) if f"txn-{idx}" in bloom)
    assert hits >= 180
    false_positive = sum(1 for idx in range(200, 260) if f"txn-{idx}" in bloom)
    assert false_positive < 60


def test_sketch_book_snapshot_roundtrip() -> None:
    book = SketchBook(width=32, depth=3, bloom_capacity=256, bloom_hashes=3)
    metrics = book.observe("event-1", customer_id="c1", device_id="d1", merchant_id="m1")
    assert metrics["replay_flag"] == 0.0
    book.observe("event-1", customer_id="c1", device_id="d1", merchant_id="m1")
    metrics = book.observe("event-2", customer_id="c2", device_id="d1", merchant_id="m1")
    assert metrics["replay_flag"] == 0.0
    snapshot = book.snapshot()
    restored = SketchBook(width=32, depth=3, bloom_capacity=256, bloom_hashes=3)
    restored.load_snapshot(snapshot)
    restored_metrics = restored.observe("event-3", customer_id="c3", device_id="d2", merchant_id="m2")
    assert restored_metrics["unique_customer_estimate"] >= metrics["unique_customer_estimate"] - 1

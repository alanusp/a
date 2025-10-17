from __future__ import annotations

import time

from app.core.abuse import HybridRateLimiter, ProofOfWorkManager


def test_pow_challenge_and_verify() -> None:
    manager = ProofOfWorkManager(difficulty=8, ttl_seconds=5)
    nonce, difficulty = manager.issue("tenant-a")
    assert difficulty == 8
    counter = 0
    solution = None
    while True:
        candidate = f"{nonce}:{counter}"
        if manager.verify("tenant-a", candidate):
            solution = candidate
            break
        counter += 1
    assert counter < 10_000
    assert solution is not None
    assert manager.verify("tenant-a", solution) is False


def test_hybrid_rate_limiter_starvation_guard() -> None:
    limiter = HybridRateLimiter(capacity=2, refill_rate_per_sec=1.0, leak_rate_per_sec=2.0, starvation_guard=2)
    tenant = "tenant-a"
    allowed = [limiter.allow(tenant, now=0.0) for _ in range(3)]
    assert allowed.count(True) >= 2
    time.sleep(0.01)
    assert limiter.allow(tenant, now=10.0) is True

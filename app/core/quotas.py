"""Tenant quota enforcement."""
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Dict


@dataclass
class QuotaDecision:
    allowed: bool
    remaining: float
    retry_after: float
    reason: str | None = None


class TokenBucket:
    def __init__(self, *, capacity: float, refill_rate: float) -> None:
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.updated = time.monotonic()

    def take(self, cost: float = 1.0) -> float:
        now = time.monotonic()
        elapsed = max(now - self.updated, 0.0)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.updated = now
        if self.tokens >= cost:
            self.tokens -= cost
            return self.tokens
        return -1.0


class TenantQuotaManager:
    def __init__(self, *, default_qps: float = 10.0, burst: float = 5.0) -> None:
        self._lock = RLock()
        self._buckets: Dict[str, TokenBucket] = {}
        self._default_qps = default_qps
        self._default_capacity = default_qps + burst

    def _bucket(self, tenant_id: str) -> TokenBucket:
        bucket = self._buckets.get(tenant_id)
        if not bucket:
            bucket = TokenBucket(capacity=self._default_capacity, refill_rate=self._default_qps)
            self._buckets[tenant_id] = bucket
        return bucket

    def check(self, tenant_id: str, *, cost: float = 1.0) -> QuotaDecision:
        with self._lock:
            bucket = self._bucket(tenant_id)
            remaining = bucket.take(cost)
            if remaining >= 0:
                return QuotaDecision(allowed=True, remaining=remaining, retry_after=0.0)
            deficit = -remaining
            retry_after = max(deficit / max(bucket.refill_rate, 0.1), 0.1)
            return QuotaDecision(
                allowed=False,
                remaining=0.0,
                retry_after=retry_after,
                reason="tenant_quota_exceeded",
            )

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {tenant: bucket.tokens for tenant, bucket in self._buckets.items()}


_MANAGER: TenantQuotaManager | None = None


def get_quota_manager() -> TenantQuotaManager:
    global _MANAGER
    if _MANAGER is None:
        from app.core.config import get_settings

        settings = get_settings()
        _MANAGER = TenantQuotaManager(
            default_qps=getattr(settings, "quota_default_qps", 10.0),
            burst=getattr(settings, "quota_burst", 5.0),
        )
    return _MANAGER

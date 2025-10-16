from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict

from app.core.config import get_settings


@dataclass(slots=True)
class AdmitDecision:
    allowed: bool
    reason: str | None = None
    retry_after: float = 0.1


class DeficitRoundRobin:
    def __init__(self, default_weight: float = 1.0) -> None:
        self._weights: Dict[str, float] = {}
        self._deficit: Dict[str, float] = {}
        self._default_weight = max(default_weight, 0.1)

    def weight(self, tenant_id: str) -> float:
        return self._weights.get(tenant_id, self._default_weight)

    def set_weight(self, tenant_id: str, weight: float) -> None:
        self._weights[tenant_id] = max(weight, 0.1)

    def admit(self, tenant_id: str, cost: float = 1.0) -> bool:
        weight = self.weight(tenant_id)
        deficit = self._deficit.get(tenant_id, 0.0) + weight
        if deficit < cost:
            self._deficit[tenant_id] = deficit
            return False
        self._deficit[tenant_id] = deficit - cost
        return True

    def snapshot(self) -> Dict[str, float]:
        return dict(self._deficit)


class SLAScheduler:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._queue = DeficitRoundRobin()
        self._lock = threading.Lock()
        self._drops: Dict[str, int] = {}
        self._seen: Dict[str, int] = {}
        self._burst: Dict[str, int] = {}
        self._max_burst = 3

    def admit(self, tenant_id: str, *, cost: float = 1.0) -> AdmitDecision:
        with self._lock:
            allowed = self._queue.admit(tenant_id, cost)
            self._seen[tenant_id] = self._seen.get(tenant_id, 0) + 1
            if allowed:
                current = self._burst.get(tenant_id, 0) + 1
                self._burst[tenant_id] = current
                if current > self._max_burst:
                    self._drops[tenant_id] = self._drops.get(tenant_id, 0) + 1
                    return AdmitDecision(
                        allowed=False,
                        reason=f"tenant {tenant_id} burst", retry_after=float(self._settings.read_timeout_seconds)
                    )
                for other in list(self._burst):
                    if other != tenant_id:
                        self._burst[other] = max(self._burst.get(other, 0) - 1, 0)
                return AdmitDecision(allowed=True)
            self._drops[tenant_id] = self._drops.get(tenant_id, 0) + 1
            retry_after = float(self._settings.read_timeout_seconds)
            return AdmitDecision(
                allowed=False,
                reason=f"tenant {tenant_id} deficit", retry_after=retry_after
            )

    def metrics(self) -> Dict[str, float]:
        with self._lock:
            data = {f"deficit.{tenant}": value for tenant, value in self._queue.snapshot().items()}
            for tenant, count in self._drops.items():
                data[f"drops.{tenant}"] = float(count)
            for tenant, count in self._seen.items():
                data[f"requests.{tenant}"] = float(count)
        return data


_SCHEDULER: SLAScheduler | None = None


def get_sla_scheduler() -> SLAScheduler:
    global _SCHEDULER
    if _SCHEDULER is None:
        _SCHEDULER = SLAScheduler()
    return _SCHEDULER

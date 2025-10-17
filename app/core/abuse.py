from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple


def _hashcash(resource: str, nonce: str, difficulty: int) -> str:
    payload = f"{resource}:{nonce}:{difficulty}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return digest


@dataclass(slots=True)
class ProofOfWorkManager:
    difficulty: int = 18
    ttl_seconds: int = 60
    _challenges: Dict[str, Tuple[str, float]] = field(default_factory=dict)

    def issue(self, resource: str) -> Tuple[str, int]:
        nonce = hashlib.sha256(f"{resource}:{time.time()}".encode()).hexdigest()
        self._challenges[resource] = (nonce, time.time())
        return nonce, self.difficulty

    def verify(self, resource: str, solution: str) -> bool:
        challenge = self._challenges.get(resource)
        if not challenge:
            return False
        nonce, issued = challenge
        if time.time() - issued > self.ttl_seconds:
            self._challenges.pop(resource, None)
            return False
        digest = _hashcash(resource, solution, self.difficulty)
        valid = digest.startswith("0" * (self.difficulty // 4))
        if valid:
            self._challenges.pop(resource, None)
        return valid


@dataclass(slots=True)
class HybridRateLimiter:
    capacity: int
    refill_rate_per_sec: float
    leak_rate_per_sec: float
    starvation_guard: int = 5
    _tokens: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _queues: Dict[str, Deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _last_timestamp: Dict[str, float] = field(default_factory=dict)

    def allow(self, tenant: str, now: float | None = None) -> bool:
        if now is None:
            now = time.time()
        tokens = self._tokens[tenant]
        last = self._last_timestamp.get(tenant, now)
        elapsed = max(now - last, 0.0)
        tokens = min(self.capacity, tokens + elapsed * self.refill_rate_per_sec)
        leak_queue = self._queues[tenant]
        while leak_queue and now - leak_queue[0] > 1 / max(self.leak_rate_per_sec, 1e-6):
            leak_queue.popleft()
        if tokens < 1.0:
            if len(leak_queue) >= self.starvation_guard:
                return False
            leak_queue.append(now)
            self._tokens[tenant] = tokens
            self._last_timestamp[tenant] = now
            return True
        self._tokens[tenant] = tokens - 1.0
        self._last_timestamp[tenant] = now
        return True

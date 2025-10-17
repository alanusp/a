from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Optional

try:  # pragma: no cover - redis optional in offline tests
    import redis
except ModuleNotFoundError:  # pragma: no cover
    redis = None  # type: ignore

from app.core.config import get_settings


class LeadershipError(RuntimeError):
    """Raised when leadership assertions fail."""


@dataclass(frozen=True)
class LeaderLease:
    role: str
    actor_id: str
    token: str
    expires_at: float

    @property
    def ttl(self) -> float:
        return max(0.0, self.expires_at - time.time())


class LeaderElector:
    """Redis-backed leader election using fencing tokens and heartbeats."""

    def __init__(
        self,
        *,
        role: str,
        client: Optional["redis.Redis"] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        if client is None:
            if redis is None:  # pragma: no cover - handled in tests
                raise RuntimeError("redis dependency unavailable")
            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self._client = client
        self._role = role
        self._ttl_ms = int(1000 * (ttl_seconds or settings.leader_ttl_seconds))
        self._key = f"hyperion:leadership:{role}"

    # Public API ---------------------------------------------------------
    def acquire(self, actor_id: str) -> LeaderLease:
        token = self._issue_token(actor_id)
        if self._client.set(self._key, token, nx=True, px=self._ttl_ms):
            return LeaderLease(self._role, actor_id, token, time.time() + self._ttl_ms / 1000)
        current = self._client.get(self._key)
        if isinstance(current, str) and current.startswith(f"{actor_id}:"):
            # Reentrant acquisition by the same actor: extend lease.
            self._client.pexpire(self._key, self._ttl_ms)
            return LeaderLease(
                self._role,
                actor_id,
                current,
                time.time() + self._ttl_ms / 1000,
            )
        raise LeadershipError(f"leader already elected for role {self._role}")

    def heartbeat(self, lease: LeaderLease) -> LeaderLease:
        self._assert_owner(lease)
        self._client.pexpire(self._key, self._ttl_ms)
        return LeaderLease(
            self._role,
            lease.actor_id,
            lease.token,
            time.time() + self._ttl_ms / 1000,
        )

    def release(self, lease: LeaderLease) -> None:
        self._assert_owner(lease)
        current = self._client.get(self._key)
        if current == lease.token:
            self._client.delete(self._key)

    def assert_leader(self, lease: LeaderLease) -> None:
        self._assert_owner(lease)

    # Internal helpers ---------------------------------------------------
    def _issue_token(self, actor_id: str) -> str:
        return f"{actor_id}:{uuid.uuid4().hex}:{int(time.time() * 1000)}"

    def _assert_owner(self, lease: LeaderLease) -> None:
        current = self._client.get(self._key)
        if current != lease.token:
            raise LeadershipError(
                "stale leadership token; another leader may have preempted this actor"
            )


__all__ = ["LeaderElector", "LeaderLease", "LeadershipError"]

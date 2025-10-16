from __future__ import annotations

import json
from typing import Any, Dict

import redis

from app.core.config import get_settings
from app.core.mtls import client_ssl_kwargs
from app.core.limits import get_limit_registry


class RedisStream:
    """Publish realtime predictions to Redis Streams for consumers and UI dashboards."""

    def __init__(self) -> None:
        settings = get_settings()
        ssl_kwargs = client_ssl_kwargs() if settings.enable_mtls else {}
        self.client = redis.Redis.from_url(
            settings.redis_url, decode_responses=True, **ssl_kwargs
        )
        self.stream_key = "hyperion:predictions"
        self._limit = get_limit_registry().for_resource("redis_stream")

    def publish(self, data: Dict[str, Any], *, stream_key: str | None = None) -> str:
        key = stream_key or self.stream_key
        length = int(self.client.xlen(key))
        decision = self._limit.assess(length)
        if not decision.allowed:
            return ""
        if decision.severity == "soft" and decision.soft_limit:
            self.client.xtrim(key, maxlen=decision.soft_limit, approximate=True)
        message_id = self.client.xadd(key, {"payload": json.dumps(data)})
        self._limit.commit(int(self.client.xlen(key)))
        return message_id

    def latest(self, count: int = 20) -> list[Dict[str, Any]]:
        entries = self.client.xrevrange(self.stream_key, count=count)
        result: list[Dict[str, Any]] = []
        for _, entry in entries:
            payload = entry.get("payload")
            if payload:
                result.append(json.loads(payload))
        return list(reversed(result))

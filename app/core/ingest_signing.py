from __future__ import annotations

import hmac
import os
import time
from hashlib import sha256
from typing import Any, Mapping

from app.core.crypto_rotate import get_key_manager

class IngestSignatureError(Exception):
    pass


class IngestSigner:
    def __init__(
        self,
        secret: str | None = None,
        *,
        ttl_seconds: int = 60,
        redis_client: Any | None = None,
    ) -> None:
        self._manager = get_key_manager()
        self.secret = (secret or os.getenv("INGEST_HMAC_SECRET", "")).encode()
        self.ttl_seconds = ttl_seconds
        if redis_client is not None:
            self.redis = redis_client
        else:
            from app.services.redis_stream import RedisStream

            self.redis = RedisStream().client

    def verify(self, headers: Mapping[str, str], nonce_key: str) -> None:
        signature = headers.get("x-ingest-signature")
        timestamp = headers.get("x-ingest-timestamp")
        nonce = headers.get("x-ingest-nonce")
        if not signature or not timestamp or not nonce:
            raise IngestSignatureError("missing signature headers")
        key_id = headers.get("x-ingest-key-id") or headers.get("X-Ingest-Key-Id")
        if key_id:
            material = self._manager.validate(purpose="ingest", key_id=key_id)
            secret = material.secret
            self._manager.audit_use(
                purpose="ingest",
                key=material,
                context={"nonce": nonce, "nonce_key": nonce_key},
            )
        else:
            material = self._manager.primary("ingest")
            secret = material.secret if not self.secret else self.secret
            self._manager.audit_use(
                purpose="ingest",
                key=material,
                context={"nonce": nonce, "nonce_key": nonce_key, "implicit_key": True},
            )
        message = f"{nonce}.{timestamp}.{nonce_key}".encode()
        expected = hmac.new(secret, message, sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise IngestSignatureError("invalid signature")
        now = time.time()
        if abs(now - float(timestamp)) > self.ttl_seconds:
            raise IngestSignatureError("signature expired")
        redis_key = f"ingest:nonce:{nonce}"
        if self.redis.setnx(redis_key, str(now)):
            self.redis.expire(redis_key, int(self.ttl_seconds))
        else:
            raise IngestSignatureError("nonce already used")

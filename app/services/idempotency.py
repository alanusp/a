from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from app.core.cache import TTLCache
from app.core.durability import get_durability_manager


@dataclass(frozen=True)
class IdempotencyRecord:
    payload: Dict[str, Any]
    route: str
    status_code: int
    headers: Dict[str, str]


class IdempotencyStore:
    def __init__(self, cache: TTLCache | None = None) -> None:
        self._cache = cache or TTLCache(name="idempotency", ttl_seconds=900, max_size=2048)
        self._durability = get_durability_manager()
        self._durability.recover("idempotency", self._replay_entry)

    def _key(self, tenant_id: str, idem_key: str) -> Tuple[str, str]:
        return tenant_id, idem_key

    def get(self, tenant_id: str, idem_key: str) -> IdempotencyRecord | None:
        found, record = self._cache.get(self._key(tenant_id, idem_key))
        if not found:
            return None
        return record

    def store_success(
        self,
        tenant_id: str,
        idem_key: str,
        *,
        payload: Dict[str, Any],
        route: str,
        headers: Dict[str, str] | None = None,
    ) -> None:
        record = IdempotencyRecord(
            payload=payload,
            route=route,
            status_code=200,
            headers=headers or {},
        )
        self._cache.set(self._key(tenant_id, idem_key), record)
        self._durability.append(
            "idempotency",
            {
                "tenant_id": tenant_id,
                "key": idem_key,
                "record": {
                    "payload": payload,
                    "route": route,
                    "status_code": 200,
                    "headers": headers or {},
                },
            },
        )

    # Backwards compatibility for older call sites.
    def set(self, tenant_id: str, idem_key: str, payload: Dict[str, Any], route: str) -> None:  # pragma: no cover - legacy
        self.store_success(tenant_id, idem_key, payload=payload, route=route)

    def store_error(
        self,
        tenant_id: str,
        idem_key: str,
        *,
        detail: Dict[str, Any],
        route: str,
        headers: Dict[str, str] | None = None,
        status_code: int,
    ) -> None:
        record = IdempotencyRecord(
            payload=detail,
            route=route,
            status_code=status_code,
            headers=headers or {},
        )
        self._cache.set(self._key(tenant_id, idem_key), record)
        self._durability.append(
            "idempotency",
            {
                "tenant_id": tenant_id,
                "key": idem_key,
                "record": {
                    "payload": detail,
                    "route": route,
                    "status_code": status_code,
                    "headers": headers or {},
                },
            },
        )

    def _replay_entry(self, payload: dict[str, object]) -> None:
        tenant = str(payload.get("tenant_id", ""))
        key = str(payload.get("key", ""))
        record_payload = payload.get("record", {})
        if not isinstance(record_payload, dict) or not tenant or not key:
            return
        record = IdempotencyRecord(
            payload=record_payload.get("payload", {}),
            route=str(record_payload.get("route", "")),
            status_code=int(record_payload.get("status_code", 200)),
            headers=dict(record_payload.get("headers", {})),
        )
        self._cache.set(self._key(tenant, key), record)


_STORE: IdempotencyStore | None = None


def get_idempotency_store() -> IdempotencyStore:
    global _STORE
    if _STORE is None:
        _STORE = IdempotencyStore()
    return _STORE

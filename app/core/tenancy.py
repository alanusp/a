from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

_DEFAULT_TENANT = "public"


@dataclass(slots=True, frozen=True)
class TenantContext:
    tenant_id: str
    api_key: str | None

    def key(self, raw: str) -> str:
        return f"{self.tenant_id}:{raw}" if raw else self.tenant_id

    @property
    def metrics_namespace(self) -> str:
        return f"tenant.{self.tenant_id}"


class TenantResolver:
    """Resolve tenants from API keys and headers with safe fallbacks."""

    def __init__(self, mapping: Mapping[str, str] | None = None) -> None:
        self._mapping = dict(mapping or {})

    def resolve(self, headers: Mapping[str, str]) -> TenantContext:
        api_key = headers.get("x-api-key") or headers.get("X-API-Key")
        if api_key and api_key in self._mapping:
            tenant = self._mapping[api_key]
        else:
            tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-Id") or _DEFAULT_TENANT
        return TenantContext(tenant_id=tenant.lower(), api_key=api_key)

    def register(self, api_key: str, tenant_id: str) -> None:
        self._mapping[api_key] = tenant_id

    def quotas_key(self, tenant: TenantContext) -> str:
        return tenant.key("rate-limit")

    def slo_key(self, tenant: TenantContext, slo: str) -> str:
        return tenant.key(f"slo::{slo}")

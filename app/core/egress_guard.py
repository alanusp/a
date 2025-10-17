"""Outbound egress guard utilities."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Iterable, Mapping
from urllib.parse import urlparse


@dataclass(frozen=True)
class EgressDecision:
    host: str
    tenant_id: str
    allowed: bool
    reason: str | None = None


class OutboundEgressGuard:
    """Deny outbound HTTP unless the host has been explicitly allow-listed."""

    def __init__(
        self,
        allowlist: Mapping[str, Iterable[str]] | None = None,
        *,
        audit_path: Path | None = None,
    ) -> None:
        self._allowlist = {
            host.lower(): {tenant.lower() for tenant in tenants}
            for host, tenants in (allowlist or {}).items()
        }
        self._audit_path = audit_path or Path("artifacts/runtime/egress_denied.jsonl")
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._denials = 0

    def check(self, url: str, *, tenant_id: str = "default") -> EgressDecision:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return EgressDecision(host="", tenant_id=tenant_id, allowed=False, reason="invalid-host")
        tenants = self._allowlist.get(host)
        tenant_norm = tenant_id.lower()
        allowed = False
        if tenants:
            if "*" in tenants or tenant_norm in tenants:
                allowed = True
        if allowed:
            return EgressDecision(host=host, tenant_id=tenant_id, allowed=True)
        decision = EgressDecision(
            host=host,
            tenant_id=tenant_id,
            allowed=False,
            reason="egress-blocked",
        )
        self._record(decision)
        return decision

    def _record(self, decision: EgressDecision) -> None:
        payload = {
            "host": decision.host,
            "tenant": decision.tenant_id,
            "allowed": decision.allowed,
            "reason": decision.reason,
        }
        with self._lock:
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
            self._denials += 1

    @property
    def denials(self) -> int:
        with self._lock:
            return self._denials


_GUARD: OutboundEgressGuard | None = None


def configure_guard(mapping: Mapping[str, Iterable[str]]) -> None:
    global _GUARD
    _GUARD = OutboundEgressGuard(mapping)


def get_guard() -> OutboundEgressGuard:
    global _GUARD
    if _GUARD is None:
        _GUARD = OutboundEgressGuard({})
    return _GUARD

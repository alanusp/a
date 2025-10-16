"""Exact-once reconciliation helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from app.core.durability import get_durability_manager


@dataclass
class ReconcileMismatch:
    tenant_id: str
    key: str
    reason: str


@dataclass
class ReconcileReport:
    inspected: int
    mismatches: List[ReconcileMismatch] = field(default_factory=list)
    repaired: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "inspected": self.inspected,
            "repaired": self.repaired,
            "mismatches": [mismatch.__dict__ for mismatch in self.mismatches],
        }


class ExactOnceReconciler:
    def __init__(
        self,
        stream_offsets: Dict[str, Iterable[str]] | None = None,
        *,
        auto_repair: bool = False,
        audit_path: Path | None = None,
        durability_manager=None,
    ) -> None:
        self._durability = durability_manager or get_durability_manager()
        self._stream_offsets = {
            tenant: set(ids) for tenant, ids in (stream_offsets or {}).items()
        }
        self._auto_repair = auto_repair
        self._audit_path = audit_path or Path("artifacts/runtime/reconcile.json")
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    def reconcile(self) -> ReconcileReport:
        records = self._durability.replay("idempotency")
        report = ReconcileReport(inspected=len(records))
        for record in records:
            payload = record.payload
            tenant = str(payload.get("tenant_id", ""))
            key = str(payload.get("key", ""))
            stream_ids = self._stream_offsets.get(tenant, set())
            if key in stream_ids:
                continue
            report.mismatches.append(
                ReconcileMismatch(tenant_id=tenant, key=key, reason="missing-from-stream"),
            )
            if self._auto_repair:
                stream_ids.add(key)
                report.repaired += 1
        self._write(report)
        return report

    def _write(self, report: ReconcileReport) -> None:
        self._audit_path.write_text(json.dumps(report.to_dict(), sort_keys=True), encoding="utf-8")


def reconcile_exact_once(stream_offsets: Dict[str, Iterable[str]] | None = None) -> ReconcileReport:
    return ExactOnceReconciler(stream_offsets=stream_offsets).reconcile()

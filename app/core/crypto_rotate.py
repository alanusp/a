from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Mapping

from app.core.config import get_settings
from app.core.json_canonical import canonicalize
from app.core.audit import get_ledger


@dataclass(slots=True, frozen=True)
class KeyMaterial:
    purpose: str
    key_id: str
    secret: bytes
    not_before: datetime
    not_after: datetime
    metadata: Mapping[str, object] | None = None

    @classmethod
    def from_mapping(cls, purpose: str, payload: Mapping[str, object]) -> "KeyMaterial":
        try:
            key_id = str(payload["key_id"])
            secret = base64.b64decode(str(payload["secret"]), validate=True)
            not_before = datetime.fromisoformat(str(payload["not_before"]))
            not_after = datetime.fromisoformat(str(payload["not_after"]))
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else None
        except Exception as exc:  # pragma: no cover - defensive parsing
            raise ValueError(f"invalid key payload for {purpose}: {payload}") from exc
        return cls(
            purpose=purpose,
            key_id=key_id,
            secret=secret,
            not_before=not_before,
            not_after=not_after,
            metadata=metadata,
        )

    def to_mapping(self) -> Dict[str, object]:
        return {
            "key_id": self.key_id,
            "secret": base64.b64encode(self.secret).decode("ascii"),
            "not_before": self.not_before.isoformat(),
            "not_after": self.not_after.isoformat(),
            "metadata": dict(self.metadata or {}),
        }

    def is_active(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return self.not_before <= current <= self.not_after


class DualKeyManager:
    """Manage purpose-specific secrets with dual-key grace windows."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        settings = get_settings()
        self.manifest_path = manifest_path or settings.key_manifest_path
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._keys: Dict[str, List[KeyMaterial]] = {}
        self._load()

    # ------------------------------------------------------------------ utils
    def _default_manifest(self) -> Dict[str, List[KeyMaterial]]:
        now = datetime.now(timezone.utc)
        far = now + timedelta(days=5 * 365)
        defaults: Dict[str, List[KeyMaterial]] = {}
        for purpose in ("ingest", "pii_salt", "api", "decision_receipt"):
            secret = f"{purpose}-static-secret".encode()
            metadata: Mapping[str, object] | None = None
            if purpose == "api":
                metadata = {"tenant_id": "public"}
            defaults[purpose] = [
                KeyMaterial(
                    purpose=purpose,
                    key_id=f"{purpose}-v1",
                    secret=secret,
                    not_before=now,
                    not_after=far,
                    metadata=metadata,
                )
            ]
        return defaults

    def _load(self) -> None:
        if not self.manifest_path.exists():
            self._keys = self._default_manifest()
            self._persist()
            return
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        keys: Dict[str, List[KeyMaterial]] = {}
        for purpose, items in payload.items():
            keys[purpose] = [KeyMaterial.from_mapping(purpose, item) for item in items]
        self._keys = keys

    def _persist(self) -> None:
        payload = {purpose: [material.to_mapping() for material in materials] for purpose, materials in self._keys.items()}
        self.manifest_path.write_text(canonicalize(payload), encoding="utf-8")

    # ----------------------------------------------------------------- helpers
    def _materials(self, purpose: str) -> List[KeyMaterial]:
        if purpose not in self._keys:
            defaults = self._default_manifest()
            self._keys.setdefault(purpose, defaults.get(purpose, []))
            for other, materials in defaults.items():
                self._keys.setdefault(other, materials)
            self._persist()
        return list(self._keys[purpose])

    def active(self, purpose: str, *, now: datetime | None = None) -> List[KeyMaterial]:
        current = now or datetime.now(timezone.utc)
        return [material for material in self._materials(purpose) if material.is_active(now=current)]

    def primary(self, purpose: str, *, now: datetime | None = None) -> KeyMaterial:
        materials = sorted(self.active(purpose, now=now), key=lambda item: item.not_after, reverse=True)
        if not materials:
            raise LookupError(f"no active key for {purpose}")
        return materials[0]

    def active_api_keys(self, *, now: datetime | None = None) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for material in self.active("api", now=now):
            tenant = str((material.metadata or {}).get("tenant_id", "public"))
            try:
                api_key = material.secret.decode("utf-8")
            except UnicodeDecodeError:  # pragma: no cover - defensive fallback
                api_key = base64.b64encode(material.secret).decode("ascii")
            mapping[api_key] = tenant
        return mapping

    def audit_use(self, *, purpose: str, key: KeyMaterial, context: Mapping[str, object]) -> None:
        payload = {
            "purpose": purpose,
            "key_id": key.key_id,
            "used_at": datetime.now(timezone.utc).isoformat(),
            "context": dict(context),
        }
        get_ledger().append(event_id=f"key-use::{purpose}::{key.key_id}", payload=payload)

    def validate(self, *, purpose: str, key_id: str, now: datetime | None = None) -> KeyMaterial:
        for material in self.active(purpose, now=now):
            if material.key_id == key_id:
                return material
        raise LookupError(f"key {key_id} not active for {purpose}")

    def rotate(
        self,
        *,
        purpose: str,
        new_key_id: str,
        secret: bytes,
        not_before: datetime,
        not_after: datetime,
    ) -> None:
        with self._lock:
            materials = self._materials(purpose)
            materials.append(
                KeyMaterial(
                    purpose=purpose,
                    key_id=new_key_id,
                    secret=secret,
                    not_before=not_before,
                    not_after=not_after,
                )
            )
            self._keys[purpose] = sorted(materials, key=lambda item: item.not_before)
            self._persist()


_MANAGER: DualKeyManager | None = None


def get_key_manager() -> DualKeyManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = DualKeyManager()
    return _MANAGER

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from secrets import token_bytes

from app.core.config import get_settings
from app.core.crypto_rotate import get_key_manager


class PrivacyService:
    """Provide deterministic hashing and retention controls for sensitive fields."""

    def __init__(self, salt_path: Path | None = None, retention_days: int | None = None) -> None:
        settings = get_settings()
        self.salt_path = salt_path or settings.privacy_salt_path
        self.retention_days = retention_days or settings.retention_days
        self.dsar_dir = settings.dsar_dir
        self.dsar_dir.mkdir(parents=True, exist_ok=True)
        self.consent_path = settings.consent_state_path
        self.hold_path = self.dsar_dir / "holds.json"
        manager = get_key_manager()
        material = manager.primary("pii_salt")
        manager.audit_use(purpose="pii_salt", key=material, context={"event": "privacy_init"})
        self._salt_material = material
        self._salt = material.secret
        if not self.consent_path.exists():
            self.consent_path.write_text("v1")
        if not self.hold_path.exists():
            self.hold_path.write_text(json.dumps({}, indent=2))

    def hash_value(self, value: str) -> str:
        digest = hmac.new(self._salt, value.encode(), hashlib.sha256)
        return digest.hexdigest()

    def hash_record(self, record: dict[str, str], *, fields: Iterable[str]) -> dict[str, str]:
        payload = dict(record)
        for field in fields:
            if field in payload and payload[field] is not None:
                payload[field] = self.hash_value(str(payload[field]))
        return payload

    def record_subject_event(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        payload: dict[str, object],
    ) -> None:
        hashed = self.hash_value(subject_id)
        record = {"subject": hashed, "tenant": tenant_id, "payload": payload, "recorded_at": datetime.utcnow().isoformat()}
        path = self.dsar_dir / f"{tenant_id}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def export_subject(self, *, tenant_id: str, subject_id: str) -> list[dict[str, object]]:
        path = self.dsar_dir / f"{tenant_id}.jsonl"
        hashed = self.hash_value(subject_id)
        if not path.exists():
            return []
        exports: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("subject") == hashed:
                    exports.append(record)
        return exports

    def delete_subject(self, *, tenant_id: str, subject_id: str) -> bool:
        holds = self._active_holds()
        key = f"{tenant_id}:{self.hash_value(subject_id)}"
        if key in holds:
            entry = holds[key]
            from app.core.audit import get_ledger

            get_ledger().append(
                event_id=f"legal-hold-{key}",
                payload={"tenant": tenant_id, "subject": subject_id, "reason": entry.get("reason", "hold")},
            )
            return False
        path = self.dsar_dir / f"{tenant_id}.jsonl"
        hashed = self.hash_value(subject_id)
        if not path.exists():
            return False
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("subject") != hashed:
                    records.append(line)
        with path.open("w", encoding="utf-8") as handle:
            handle.writelines(records)
        return True

    def consent_version(self) -> str:
        return self.consent_path.read_text().strip()

    def update_consent(self, version: str) -> str:
        self.consent_path.write_text(version.strip())
        return self.consent_version()

    def _active_holds(self) -> dict[str, dict[str, object]]:
        if not self.hold_path.exists():
            return {}
        payload = json.loads(self.hold_path.read_text())
        now = datetime.utcnow()
        active: dict[str, dict[str, object]] = {}
        changed = False
        for key, entry in payload.items():
            expires_at = entry.get("expires_at")
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at)
                except ValueError:
                    continue
                if expiry < now:
                    changed = True
                    continue
            active[key] = entry
        if changed:
            self.hold_path.write_text(json.dumps(active, indent=2, sort_keys=True))
        return active

    def apply_legal_hold(self, tenant_id: str, subject_id: str, *, reason: str, expires_at: datetime) -> dict[str, object]:
        holds = self._active_holds()
        key = f"{tenant_id}:{self.hash_value(subject_id)}"
        entry = {"reason": reason, "expires_at": expires_at.isoformat()}
        holds[key] = entry
        self.hold_path.write_text(json.dumps(holds, indent=2, sort_keys=True))
        from app.core.audit import get_ledger

        get_ledger().append(
            event_id=f"legal-hold-set-{key}",
            payload={"tenant": tenant_id, "subject": subject_id, "reason": reason, "expires_at": entry["expires_at"]},
        )
        return entry

    def release_legal_hold(self, tenant_id: str, subject_id: str) -> None:
        holds = self._active_holds()
        key = f"{tenant_id}:{self.hash_value(subject_id)}"
        if key in holds:
            holds.pop(key)
            self.hold_path.write_text(json.dumps(holds, indent=2, sort_keys=True))

    def rotate_salt(self) -> None:
        manager = get_key_manager()
        start = datetime.now(timezone.utc)
        manager.rotate(
            purpose="pii_salt",
            new_key_id=f"pii_salt-{int(start.timestamp())}",
            secret=token_bytes(32),
            not_before=start,
            not_after=start + timedelta(days=max(self.retention_days or 30, 3650)),
        )
        self._salt_material = manager.primary("pii_salt")
        self._salt = self._salt_material.secret

    def purge_before(self, cutoff: datetime, records: list[dict[str, object]], *, field: str) -> list[dict[str, object]]:
        pruned: list[dict[str, object]] = []
        for record in records:
            timestamp = record.get(field)
            if isinstance(timestamp, datetime) and timestamp < cutoff:
                continue
            if isinstance(timestamp, str):
                try:
                    parsed = datetime.fromisoformat(timestamp)
                except ValueError:
                    pruned.append(record)
                else:
                    if parsed < cutoff:
                        continue
                    record[field] = parsed
                    pruned.append(record)
            else:
                pruned.append(record)
        return pruned

    def retention_cutoff(self) -> datetime:
        return datetime.utcnow() - timedelta(days=self.retention_days)

    def _load_salt(self) -> bytes:
        if self.salt_path.exists():
            return self.salt_path.read_bytes()
        salt = os.urandom(32)
        self.salt_path.write_bytes(salt)
        return salt

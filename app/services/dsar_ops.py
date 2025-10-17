from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict

from app.core.audit import get_ledger
from app.core.config import get_settings
from app.core.crypto_rotate import get_key_manager
from app.core.json_canonical import canonicalize


def _luhn_checksum(value: str) -> int:
    total = 0
    reverse_digits = value[::-1]
    for idx, char in enumerate(reverse_digits):
        digit = int(char)
        if idx % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10


def _format_preserving_mask(value: str, salt: str) -> str:
    if not value.isdigit():
        digest = hashlib.sha256((value + salt).encode()).hexdigest()
        return digest[: len(value)]
    hashed = hashlib.sha256((value + salt).encode()).digest()
    number = int.from_bytes(hashed, "big")
    base = str(number).zfill(len(value))[: len(value) - 1]
    checksum = (10 - _luhn_checksum(base + "0")) % 10
    return base + str(checksum)


@dataclass(slots=True)
class DSAROperator:
    salt: str
    certificate_dir: Path = Path(get_settings().dsar_dir)

    def __post_init__(self) -> None:
        self.certificate_dir.mkdir(parents=True, exist_ok=True)
        manager = get_key_manager()
        material = manager.primary("pii_salt")
        manager.audit_use(purpose="pii_salt", key=material, context={"event": "dsar"})
        if not getattr(self, "salt", None):
            self.salt = hashlib.sha256(material.secret).hexdigest()

    def export(self, payload: Dict[str, str]) -> Dict[str, str]:
        masked = {key: _format_preserving_mask(value, self.salt) for key, value in payload.items()}
        ledger = get_ledger()
        ledger.append(event_id="dsar_export", payload=masked)
        return masked

    def delete(self, keys: Dict[str, str]) -> Dict[str, str]:
        ledger = get_ledger()
        timestamp = datetime.utcnow().isoformat()
        event_id = f"dsar_delete:{keys.get('tenant_id','unknown')}:{keys.get('subject_id','unknown')}:{timestamp}"
        ledger.append(event_id=event_id, payload=keys)
        proof = [
            {"position": item.position, "hash": item.hash}
            for item in ledger.proof(event_id)
        ]
        canonical_payload = canonicalize(keys)
        certificate = {
            "event_id": event_id,
            "issued_at": timestamp,
            "payload": keys,
            "root": ledger.root(),
            "proof": proof,
            "payload_canonical": canonical_payload,
        }
        certificate["signature"] = hashlib.sha256(canonicalize(certificate).encode("utf-8")).hexdigest()
        cert_path = self.certificate_dir / f"cert_{keys.get('subject_id','unknown')}.json"
        cert_path.write_text(canonicalize(certificate), encoding="utf-8")
        return {**keys, "certificate": str(cert_path)}

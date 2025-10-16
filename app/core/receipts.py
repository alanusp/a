from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_hex

from app.core.crypto_rotate import get_key_manager
from app.core.json_canonical import canonicalize


@dataclass(slots=True, frozen=True)
class DecisionReceipt:
    identifier: str
    signature: str
    issued_at: str


def issue_decision_receipt(payload: dict[str, object]) -> DecisionReceipt:
    """Sign decision payloads for high-value actions."""

    manager = get_key_manager()
    material = manager.primary("decision_receipt")
    manager.audit_use(purpose="decision_receipt", key=material, context={"event": "issue"})
    identifier = token_hex(8)
    issued_at = datetime.now(timezone.utc).isoformat()
    envelope = payload | {"receipt_id": identifier, "issued_at": issued_at}
    canonical = canonicalize(envelope)
    signature = hmac.new(material.secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return DecisionReceipt(identifier=identifier, signature=signature, issued_at=issued_at)

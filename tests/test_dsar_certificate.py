from __future__ import annotations

import json
import hashlib
from pathlib import Path

from app.services.dsar_ops import DSAROperator


def test_dsar_certificate_signature(tmp_path: Path) -> None:
    operator = DSAROperator(salt="seed", certificate_dir=tmp_path)
    payload = {"tenant_id": "tenant", "subject_id": "subject"}
    result = operator.delete(dict(payload))
    cert_path = Path(result["certificate"])
    certificate = json.loads(cert_path.read_text(encoding="utf-8"))
    signature = certificate.pop("signature")
    canonical = json.dumps(certificate, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == signature

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.crypto_rotate import DualKeyManager


def test_dual_key_rotation(tmp_path: Path) -> None:
    manifest = tmp_path / "keys.json"
    manager = DualKeyManager(manifest_path=manifest)
    now = datetime.now(timezone.utc)
    manager.rotate(
        purpose="ingest",
        new_key_id="ingest-v2",
        secret=b"rotated-secret",
        not_before=now,
        not_after=now + timedelta(days=30),
    )
    active = manager.active("ingest", now=now + timedelta(days=1))
    assert any(material.key_id == "ingest-v2" for material in active)
    mapping = manager.active_api_keys()
    assert mapping["api-static-secret"] == "public"

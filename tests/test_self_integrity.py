from __future__ import annotations

import json
from pathlib import Path

from app.core.runtime_state import clear_read_only, is_read_only
from app.core.self_integrity import IntegrityMonitor


def test_integrity_monitor_detects_mismatch(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"hello")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_state": {"path": str(artifact), "sha256": "deadbeef"},
            }
        ),
        encoding="utf-8",
    )
    monitor = IntegrityMonitor(manifest_path=manifest, status_path=tmp_path / "status.json", interval_seconds=60)
    assert not monitor.verify_once()
    readonly, reason = is_read_only()
    assert readonly and reason == "integrity_mismatch"

    # fix manifest to match digest
    digest = "5d41402abc4b2a76b9719d911017c592"  # md5 of hello but manifest wants sha256 -> adjust
    # compute sha256 instead
    import hashlib

    digest = hashlib.sha256(b"hello").hexdigest()
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_state": {"path": str(artifact), "sha256": digest},
            }
        ),
        encoding="utf-8",
    )
    assert monitor.verify_once() is True
    readonly, reason = is_read_only()
    assert not readonly
    clear_read_only("integrity_mismatch")

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.versioning import VersionMismatchError, verify_artifacts


def test_verify_artifacts_passes(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    target = tmp_path / "file.json"
    target.write_text("{}", encoding="utf-8")
    from app.core.versioning import _digest_file  # type: ignore[attr-defined]

    manifest.write_text(
        (
            "{"
            '"schema_version": 1,'
            '"model": {"path": "' + str(target) + '", "sha256": "' + _digest_file(target) + '"}'
            "}"
        ),
        encoding="utf-8",
    )
    verify_artifacts(manifest)


def test_verify_artifacts_detects_mismatch(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    target = tmp_path / "file.json"
    target.write_text("{}", encoding="utf-8")
    manifest.write_text(
        (
            "{"
            '"schema_version": 1,'
            '"model": {"path": "' + str(target) + '", "sha256": "deadbeef"}'
            "}"
        ),
        encoding="utf-8",
    )
    with pytest.raises(VersionMismatchError):
        verify_artifacts(manifest)

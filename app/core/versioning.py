from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

_DEFAULT_MANIFEST = Path("artifacts/version_manifest.json")
_ENV_ALLOW_SKEW = "ALLOW_VERSION_SKEW"


@dataclass(frozen=True)
class ArtifactRecord:
    name: str
    path: Path
    sha256: str

    @classmethod
    def from_mapping(cls, name: str, payload: Dict[str, str]) -> "ArtifactRecord":
        path = Path(payload["path"]).expanduser().resolve()
        return cls(name=name, path=path, sha256=payload["sha256"])


class VersionMismatchError(RuntimeError):
    pass


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> tuple[int, list[ArtifactRecord]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = int(payload.get("schema_version", 0))
    records: list[ArtifactRecord] = []
    for name, meta in payload.items():
        if name == "schema_version":
            continue
        if not isinstance(meta, dict) or "path" not in meta or "sha256" not in meta:
            raise VersionMismatchError(f"invalid manifest entry for {name}")
        records.append(ArtifactRecord.from_mapping(name, meta))
    return schema_version, records


def verify_artifacts(manifest_path: Path | None = None) -> None:
    if os.getenv(_ENV_ALLOW_SKEW, "0") in {"1", "true", "TRUE"}:
        return
    manifest_file = manifest_path or _DEFAULT_MANIFEST
    if not manifest_file.exists():
        raise VersionMismatchError(f"manifest missing at {manifest_file}")
    schema_version, records = _load_manifest(manifest_file)
    if schema_version <= 0:
        raise VersionMismatchError("invalid schema version in manifest")

    mismatches: list[str] = []
    missing: list[str] = []
    for record in records:
        if not record.path.exists():
            missing.append(record.name)
            continue
        digest = _digest_file(record.path)
        if digest != record.sha256:
            mismatches.append(f"{record.name}: expected {record.sha256}, got {digest}")

    if missing or mismatches:
        detail = []
        if missing:
            detail.append(f"missing: {', '.join(sorted(missing))}")
        if mismatches:
            detail.append("mismatches: " + "; ".join(mismatches))
        raise VersionMismatchError("; ".join(detail))


__all__ = ["verify_artifacts", "VersionMismatchError"]

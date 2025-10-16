#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "repro"
BUNDLE_PATH = OUTPUT_DIR / "bundle.tgz"
CHECKSUM_PATH = OUTPUT_DIR / "bundle.sha256"

COLLECT = [
    ROOT / "artifacts" / "version_manifest.json",
    ROOT / "artifacts" / "openapi" / "current.json",
    ROOT / "artifacts" / "golden",
    ROOT / "feature_repo" / "feature_store.yaml",
    ROOT / "feature_repo" / "entities.py" if (ROOT / "feature_repo" / "entities.py").exists() else None,
    ROOT / "requirements.lock",
    ROOT / "flags",
]


def _iter_paths() -> list[Path]:
    paths: list[Path] = []
    for entry in COLLECT:
        if entry is None or not entry.exists():
            continue
        if entry.is_dir():
            for sub in entry.rglob("*"):
                if sub.is_file():
                    paths.append(sub)
        else:
            paths.append(entry)
    return paths


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = _iter_paths()
    with tarfile.open(BUNDLE_PATH, "w:gz") as archive:
        for path in paths:
            archive.add(path, arcname=path.relative_to(ROOT))
    digest = hashlib.sha256()
    with BUNDLE_PATH.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    CHECKSUM_PATH.write_text(digest.hexdigest() + "\n", encoding="utf-8")
    print(f"created bundle at {BUNDLE_PATH}")


if __name__ == "__main__":
    main()

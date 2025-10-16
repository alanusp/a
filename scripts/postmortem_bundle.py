#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

BUNDLE_ROOT = Path("artifacts/postmortem")
DEFAULT_FILES = [
    Path("artifacts/version_manifest.json"),
    Path("artifacts/integrity_status.json"),
    Path("artifacts/disk_guard.json"),
    Path("artifacts/limit_status.json"),
    Path("artifacts/perf/burn_metrics.json"),
    Path("artifacts/diag"),
    Path("artifacts/runtime/drain_status.json"),
    Path("artifacts/runtime/crashloop.json"),
    Path("artifacts/wal/manifest.json"),
    Path("artifacts/diag/thread_dump.txt"),
]


def _gather_files(extra: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for item in list(DEFAULT_FILES) + list(extra):
        if item.exists():
            files.append(item)
    return files


def build_bundle(extra: Iterable[Path] = ()) -> Path:
    BUNDLE_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_path = BUNDLE_ROOT / f"bundle-{timestamp}.tgz"
    files = _gather_files(extra)
    with tarfile.open(bundle_path, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(Path(".")))
    (BUNDLE_ROOT / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": timestamp,
                "files": [str(path) for path in files],
                "bundle": str(bundle_path),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return bundle_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a postmortem evidence bundle")
    parser.add_argument("paths", nargs="*", help="Additional paths to include")
    args = parser.parse_args()
    extra = [Path(p) for p in args.paths]
    bundle = build_bundle(extra)
    print(bundle)


if __name__ == "__main__":
    main()

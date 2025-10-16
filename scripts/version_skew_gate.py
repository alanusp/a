from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.versioning import VersionMismatchError, verify_artifacts


def run(manifest: Path | None, update: bool) -> int:
    manifest_path = manifest or Path("artifacts/version_manifest.json")
    if update:
        manifest_data = _rebuild_manifest(manifest_path)
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        print(f"updated manifest at {manifest_path}")
        return 0
    try:
        verify_artifacts(manifest_path)
    except VersionMismatchError as exc:  # pragma: no cover - exercised by CLI
        print(f"version skew detected: {exc}", file=sys.stderr)
        return 1
    return 0


def _rebuild_manifest(manifest_path: Path) -> dict[str, object]:
    from app.core.versioning import _digest_file  # type: ignore[attr-defined]

    targets = {
        "model_state": Path("artifacts/model_state_dict.json"),
        "calibration": Path("artifacts/calibration.json"),
        "feature_store": Path("feature_repo/feature_store.yaml"),
        "openapi": Path("artifacts/openapi/baseline.json"),
    }
    data: dict[str, object] = {"schema_version": 1}
    for name, path in targets.items():
        data[name] = {"path": str(path), "sha256": _digest_file(path)}
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Check artifact version skew")
    parser.add_argument("--manifest", type=Path, default=None, help="Path to manifest file")
    parser.add_argument("--update", action="store_true", help="Rewrite manifest with current digests")
    args = parser.parse_args()
    return run(args.manifest, args.update)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

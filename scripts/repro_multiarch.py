#!/usr/bin/env python3
"""Compare reproducible digests for multi-arch images."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

DIGEST_DIR = Path("artifacts/repro")


def _load_digest(arch: str) -> str:
    path = DIGEST_DIR / f"{arch}.sha256"
    if not path.exists():
        raise FileNotFoundError(f"missing digest for {arch}: {path}")
    return path.read_text(encoding="utf-8").strip()


def compare() -> Dict[str, str]:
    amd = _load_digest("amd64")
    arm = _load_digest("arm64")
    if amd != arm:
        raise RuntimeError("multi-arch digests differ; build not reproducible")
    return {"amd64": amd, "arm64": arm}


def main() -> None:
    result = compare()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()

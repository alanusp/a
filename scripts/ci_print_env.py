#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
from pathlib import Path

FIELDS = [
    "CI",
    "GITHUB_RUN_ID",
    "GITHUB_REF",
    "PYTHONPATH",
    "NODE_VERSION",
    "PLAYWRIGHT_BROWSERS_PATH",
]


def main() -> None:
    print("=== Runtime ===")
    print(f"python: {platform.python_version()}")
    print(f"platform: {platform.platform()}")
    for field in FIELDS:
        if field in os.environ:
            print(f"{field}={os.environ[field]}")
    assets = list(Path("docs/assets").glob("*.png"))
    print("=== Screenshots ===")
    for asset in assets:
        print(f"{asset} -> {asset.stat().st_size} bytes")


if __name__ == "__main__":
    main()

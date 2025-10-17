#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.diagnostics import build_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Build diagnostics bundle")
    parser.add_argument("paths", nargs="*", type=Path, help="Additional files to include")
    args = parser.parse_args()
    bundle = build_bundle(args.paths)
    print(bundle)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.flags import get_feature_flags


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate schema changes against feature flags")
    parser.add_argument("--schema-diff", required=True, help="Path to generated schema diff JSON")
    parser.add_argument("--required-flag", required=True, help="Flag that must be enabled for breaking change")
    args = parser.parse_args()

    diff_path = Path(args.schema_diff)
    if not diff_path.exists():
        raise SystemExit("schema diff missing")
    diff = json.loads(diff_path.read_text())
    breaking = diff.get("breaking", False)
    if not breaking:
        print("no breaking schema change detected")
        return
    flags = get_feature_flags()
    if not flags.enabled(args.required_flag):
        raise SystemExit(f"breaking schema change requires feature flag {args.required_flag}")
    print("breaking change permitted by feature flag")


if __name__ == "__main__":
    main()

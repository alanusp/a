#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.limits import get_limit_registry

REPORT_PATH = Path("artifacts/limit_status.json")


def main() -> None:
    registry = get_limit_registry()
    report = registry.report()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    hard = [name for name, status in report.items() if status.get("severity") == "hard"]
    if hard:
        raise SystemExit(f"hard cap breached for: {', '.join(hard)}")
    print("resource caps within bounds")


if __name__ == "__main__":
    main()

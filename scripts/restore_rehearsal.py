#!/usr/bin/env python3
"""Disaster restore rehearsal script."""
from __future__ import annotations

import json
from pathlib import Path

from app.core.durability import get_durability_manager


def rehearse() -> Path:
    manager = get_durability_manager()
    records = manager.replay("idempotency")
    report = {
        "channel": "idempotency",
        "records": len(records),
        "verified": bool(records),
    }
    path = Path("artifacts/restore/report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    return path


def main() -> None:
    path = rehearse()
    print(path)


if __name__ == "__main__":  # pragma: no cover
    main()

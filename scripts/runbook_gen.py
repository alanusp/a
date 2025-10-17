#!/usr/bin/env python3
"""Generate an incident runbook bundle."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

SOURCES = {
    "drain": Path("artifacts/runtime/drain_status.json"),
    "crashloop": Path("artifacts/runtime/crashloop.json"),
    "wal": Path("artifacts/runtime/leak_sentinel.json"),
    "reconcile": Path("artifacts/runtime/reconcile.json"),
}


def gather() -> Dict[str, object]:
    payload: Dict[str, object] = {}
    for name, path in SOURCES.items():
        if path.exists():
            payload[name] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def build() -> Path:
    bundle = gather()
    out_dir = Path("artifacts/runbook")
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "runbook.json"
    output.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    return output


def main() -> None:
    print(build())


if __name__ == "__main__":  # pragma: no cover
    main()

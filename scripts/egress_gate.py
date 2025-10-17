#!/usr/bin/env python3
"""Fail if outbound egress attempts were recorded."""
from __future__ import annotations

from pathlib import Path

AUDIT_FILE = Path("artifacts/runtime/egress_denied.jsonl")


def main() -> int:
    if AUDIT_FILE.exists():
        lines = [line for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            print("Outbound egress attempts detected:")
            for line in lines:
                print(line)
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    repo = Path(".")
    collisions: dict[str, list[str]] = {}
    for path in repo.rglob("*"):
        if any(part.startswith(".git") for part in path.parts):
            continue
        if not path.is_file():
            continue
        lowered = str(path).lower()
        collisions.setdefault(lowered, []).append(str(path))
    offenders = {key: value for key, value in collisions.items() if len(value) > 1}
    report = Path("artifacts/case_collisions.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(offenders, indent=2, sort_keys=True))
    if offenders:
        raise SystemExit("case-insensitive path collisions detected")
    print("Case-collision gate passed")


if __name__ == "__main__":
    main()

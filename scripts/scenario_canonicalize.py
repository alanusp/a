#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

MAX_BYTES = 128 * 1024
MAX_DEPTH = 16

try:  # pragma: no cover - optional dependency
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback to JSON subset
    yaml = None


def _check_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("yaml document too deep")
    if isinstance(value, dict):
        for child in value.values():
            _check_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_depth(child, depth + 1)


def _validate(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if len(text) > MAX_BYTES:
        raise ValueError(f"{path} exceeds size budget")
    if "&" in text or "*" in text:
        raise ValueError(f"{path} contains YAML anchors or aliases")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    _check_depth(data)
    return data


def main() -> None:
    base = Path("scenarios")
    output_dir = Path("artifacts/scenarios")
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(base.glob("*.yaml")):
        data = _validate(path)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        (output_dir / f"{path.stem}.json").write_text(canonical)
    print("Scenario canonicalisation complete")


if __name__ == "__main__":
    main()

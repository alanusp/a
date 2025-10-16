#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

try:  # pragma: no cover - optional dependency
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback to JSON subset
    yaml = None

MAX_BYTES = 128 * 1024
MAX_DEPTH = 16


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
    failures: dict[str, str] = {}
    for path in sorted(base.glob("*.yaml")):
        try:
            _validate(path)
        except Exception as exc:  # noqa: BLE001 - gate script
            failures[str(path)] = str(exc)
    report = Path("artifacts/yaml_safety_report.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(failures, indent=2, sort_keys=True))
    if failures:
        raise SystemExit("YAML safety violations detected")
    print("YAML safety gate passed")


if __name__ == "__main__":
    main()

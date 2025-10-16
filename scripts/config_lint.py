#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict

ENV_FILE = Path(".env.example")
REPORT_PATH = Path("artifacts/config_lint.json")
SEARCH_ROOTS = [Path("app"), Path("scripts"), Path("streaming"), Path("console"), Path("graph"), Path("policy"), Path("quality"), Path("security"), Path("rules"), Path("sketches"), Path("adversary")]
ENV_PATTERN = re.compile(r"os\.getenv\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*(['\"])(.*?)\2)?")


def _discover_env_defaults() -> Dict[str, str]:
    defaults: Dict[str, str] = {}
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for match in ENV_PATTERN.finditer(text):
                key = match.group(1)
                if key in defaults:
                    continue
                default = match.group(3) or ""
                defaults[key] = default
    return defaults


def _parse_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main() -> None:
    defaults = _discover_env_defaults()
    env_values = _parse_env(ENV_FILE)
    expected = set(defaults)
    missing = sorted(expected - env_values.keys())
    unknown = sorted(set(env_values) - expected)

    normalized: Dict[str, str] = {}
    for key in sorted(expected):
        if key in env_values:
            normalized[key] = env_values[key]
        else:
            normalized[key] = defaults.get(key, "")
    ENV_FILE.write_text(
        "\n".join(f"{key}={normalized[key]}" for key in sorted(normalized)) + "\n",
        encoding="utf-8",
    )

    report = {
        "missing": missing,
        "unknown": unknown,
        "total_expected": len(expected),
        "total_defined": len(env_values),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if missing or unknown:
        raise SystemExit("config lint found issues")
    print("config lint ok")


if __name__ == "__main__":
    main()

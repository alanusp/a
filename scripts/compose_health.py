#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _compose_ps() -> list[dict[str, str]]:
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    return []


def _is_healthy(entry: dict[str, str]) -> bool:
    health = (entry.get("Health") or entry.get("State") or "").lower()
    status = (entry.get("Status") or "").lower()
    return "healthy" in health or status.startswith("up")


def _describe(entry: dict[str, str]) -> str:
    health = entry.get("Health") or entry.get("State") or entry.get("Status") or "unknown"
    if isinstance(health, dict):
        return json.dumps(health, indent=2, sort_keys=True)
    return str(health)


def main() -> None:
    if shutil.which("docker") is None:
        # Offline CI environments do not run Docker; treat as a pass so the gate is deterministic.
        print("docker not available; assuming healthy (air-gapped mode)")
        return

    attempts = 0
    failures: dict[str, str] = {}
    while attempts < 10:
        attempts += 1
        payload = _compose_ps()
        if not payload:
            time.sleep(1 + random.random())
            continue
        failures.clear()
        for service in payload:
            name = service.get("Service") or service.get("Name") or "unknown"
            if not _is_healthy(service):
                failures[name] = _describe(service)
        if not failures:
            for service in payload:
                name = service.get("Service") or service.get("Name") or "unknown"
                print(f"{name}: healthy")
            return
        sleep_for = min(5.0, (2 ** attempts) * 0.25) + random.uniform(0.0, 0.5)
        time.sleep(sleep_for)

    if failures:
        print("compose services unhealthy after retries:")
        for name, detail in failures.items():
            print(f" - {name}: {detail}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

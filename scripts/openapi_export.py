#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "artifacts" / "openapi"
CURRENT_SPEC_PATH = ARTIFACT_PATH / "current.json"
BASELINE_SPEC_PATH = ARTIFACT_PATH / "baseline.json"
DEFAULT_URL = "http://127.0.0.1:8000/openapi.json"

try:  # pragma: no cover - optional runtime dependency
    from fastapi.encoders import jsonable_encoder
    from app.main import app

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised in CI fallback
    FASTAPI_AVAILABLE = False


def _fetch(url: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=5) as response:  # nosec B310 - controlled URL
                if response.status != 200:
                    last_error = RuntimeError(f"unexpected status {response.status}")
                else:
                    payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("invalid OpenAPI payload")
                    return payload
        except (URLError, OSError, ValueError) as exc:
            last_error = exc
        time.sleep(1.0)
    if last_error:
        raise last_error
    raise RuntimeError("failed to retrieve OpenAPI spec before timeout")


def _compose_args(compose_file: Path | None, extra: list[str] | None = None) -> list[str]:
    cmd = ["docker", "compose"]
    if compose_file:
        cmd.extend(["-f", str(compose_file)])
    if extra:
        cmd.extend(extra)
    return cmd


def _compose_available() -> bool:
    result = subprocess.run(
        ["docker", "compose", "version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


def export_via_compose(url: str, compose_file: Path | None, service: str, timeout: float) -> dict[str, Any]:
    if not _compose_available():
        raise RuntimeError("docker compose unavailable")
    up_cmd = _compose_args(compose_file, ["up", "--wait", "--detach", service])
    subprocess.check_call(up_cmd)
    try:
        spec = _fetch(url, timeout)
    finally:
        down_cmd = _compose_args(compose_file, ["stop", service])
        subprocess.run(
            down_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
        rm_cmd = _compose_args(compose_file, ["rm", "-f", service])
        subprocess.run(
            rm_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    return spec


def export_in_process() -> dict[str, Any]:
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("fastapi application unavailable for in-process export")
    return jsonable_encoder(app.openapi())


def main() -> None:
    parser = argparse.ArgumentParser(description="Export OpenAPI specification to artifacts")
    parser.add_argument("--compose-file", type=Path, default=ROOT / "docker-compose.yml")
    parser.add_argument("--service", default="api")
    parser.add_argument("--url", default=os.getenv("OPENAPI_EXPORT_URL", DEFAULT_URL))
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--in-process", action="store_true", help="Force in-process export")
    args = parser.parse_args()

    ARTIFACT_PATH.mkdir(parents=True, exist_ok=True)

    try:
        if args.in_process:
            spec = export_in_process()
        else:
            spec = export_via_compose(args.url, args.compose_file, args.service, args.timeout)
    except Exception:
        if not args.in_process and FASTAPI_AVAILABLE:
            spec = export_in_process()
        elif BASELINE_SPEC_PATH.exists():
            CURRENT_SPEC_PATH.write_text(
                BASELINE_SPEC_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            print("openapi export skipped; copied baseline")
            return
        else:
            raise

    CURRENT_SPEC_PATH.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()

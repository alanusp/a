from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

THRESHOLD_BYTES = 5 * 1024 * 1024
ALLOWLIST_PATH = Path("scripts/git_hygiene_allowlist.json")


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


def load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    return set(json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8")))


def check_sizes() -> list[str]:
    allow = load_allowlist()
    offenders: list[str] = []
    for path in tracked_files():
        if not path.exists():
            continue
        if str(path) in allow:
            continue
        size = path.stat().st_size
        if size > THRESHOLD_BYTES:
            offenders.append(f"{path} ({size} bytes)")
    return offenders


def recent_commit_scan() -> list[str]:
    output = subprocess.check_output([
        "git",
        "log",
        "--since=30.days",
        "--pretty=format:%H",
    ], text=True)
    commits = [line.strip() for line in output.splitlines() if line.strip()]
    patterns = ["PRIVATE KEY", "BEGIN RSA", "AWS_SECRET"]
    hits: list[str] = []
    for commit in commits:
        diff = subprocess.check_output([
            "git",
            "show",
            commit,
        ], text=True, stderr=subprocess.DEVNULL)
        upper = diff.upper()
        for pattern in patterns:
            if pattern in upper:
                hits.append(f"{commit}:{pattern}")
    return hits


def main() -> int:
    failures = []
    offenders = check_sizes()
    if offenders:
        print("Large tracked files detected:")
        for item in offenders:
            print(" -", item)
        failures.append("size")
    secrets = recent_commit_scan()
    if secrets:
        print("Potential secret strings in recent commits:")
        for item in secrets:
            print(" -", item)
        failures.append("secrets")
    if failures:
        return 1
    print("git hygiene ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

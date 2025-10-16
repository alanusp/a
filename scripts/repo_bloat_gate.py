#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "scripts" / "repo_bloat_allowlist.json"
DEFAULT_MAX_MB = 5


def _git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
        timeout=30,
    )
    return [ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as handle:
            head = handle.read(100)
    except UnicodeDecodeError:
        return False
    return head.startswith("version https://git-lfs.github.com/spec/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce repository bloat limits")
    parser.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB)
    args = parser.parse_args()

    allowlist = set()
    if ALLOWLIST.exists():
        allowlist = set(json.loads(ALLOWLIST.read_text(encoding="utf-8")))

    failures: list[str] = []
    for path in _git_files():
        if not path.exists():
            continue
        rel = path.relative_to(ROOT)
        if rel.as_posix() in allowlist:
            continue
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > args.max_mb and not _is_lfs_pointer(path):
            failures.append(f"{rel}: {size_mb:.2f}MB exceeds {args.max_mb}MB and is not managed by git-lfs")
    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)
    print("repository bloat gate passed")


if __name__ == "__main__":
    main()

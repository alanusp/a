from __future__ import annotations

import re
from pathlib import Path

EXCLUDE_DIRS = {".git", "vendor", "node_modules", "artifacts"}
PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"secret_key\s*=\s*['\"]?[A-Za-z0-9+/]{20,}"),
]


def should_scan(path: Path) -> bool:
    return all(part not in EXCLUDE_DIRS for part in path.parts)


def scan_directory(root: Path) -> list[tuple[Path, str]]:
    findings: list[tuple[Path, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or not should_scan(path.relative_to(root)):
            continue
        text = path.read_text(errors="ignore")
        for pattern in PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append((path, match.group(0)))
    return findings


def main() -> int:
    findings = scan_directory(Path.cwd())
    if findings:
        details = ", ".join(f"{path}:{secret}" for path, secret in findings)
        raise SystemExit(f"potential secrets detected: {details}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

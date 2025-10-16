from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PII_PATTERNS = {
    "card": re.compile(r"\b\d{12,19}\b"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

ALLOWLIST_PATH = Path("scripts/redaction_allowlist.json")


def _load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    return set(json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8")))


def scan_path(path: Path, allowlist: set[str]) -> list[str]:
    hits: list[str] = []
    for file in path.rglob("*.log"):
        content = file.read_text(encoding="utf-8", errors="ignore")
        fingerprint = f"{file}:{hash(content)}"
        if fingerprint in allowlist:
            continue
        for name, pattern in PII_PATTERNS.items():
            if pattern.search(content):
                hits.append(f"{file}:{name}")
                break
    return hits


def main(argv: list[str]) -> int:
    base = Path(argv[1]) if len(argv) > 1 else Path("artifacts")
    allowlist = _load_allowlist()
    hits = scan_path(base, allowlist)
    if hits:
        print("Redaction gate failed; PII detected:")
        for hit in hits:
            print(f" - {hit}")
        return 1
    print("Redaction gate passed; no raw PII found.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main(sys.argv))

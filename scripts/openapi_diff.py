#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

BASELINE_PATH = Path("artifacts/openapi/baseline.json")
CURRENT_PATH = Path("artifacts/openapi/current.json")
SCHEMA_DIFF_PATH = Path("artifacts/schema_diff.json")
CHANGELOG_PATH = Path("docs/offline_changelog.md")
MIGRATION_NOTE_PATH = Path("docs/schema_migrations.md")
GOLDEN_DIR = Path("artifacts/golden")


def _canonical_operations(spec: Dict[str, object]) -> Dict[str, str]:
    operations: Dict[str, str] = {}
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return operations
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            method_key = method.lower()
            if method_key not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            key = f"{method_key.upper()} {path}"
            operations[key] = json.dumps(operation, sort_keys=True)
    return operations


def _classify_diff(baseline: Dict[str, str], current: Dict[str, str]) -> Dict[str, list[str]]:
    baseline_keys = set(baseline)
    current_keys = set(current)
    added = sorted(current_keys - baseline_keys)
    removed = sorted(baseline_keys - current_keys)
    modified = sorted(
        key
        for key in baseline_keys & current_keys
        if baseline[key] != current[key]
    )
    return {"added": added, "removed": removed, "modified": modified}


def _classification(diff: Dict[str, list[str]]) -> str:
    if diff["removed"] or diff["modified"]:
        return "major"
    if diff["added"]:
        return "minor"
    return "patch"


def _ensure_migration_note() -> None:
    if not MIGRATION_NOTE_PATH.exists() or not MIGRATION_NOTE_PATH.read_text(encoding="utf-8").strip():
        raise SystemExit("breaking schema change requires docs/schema_migrations.md entry")


def _write_diff(diff: Dict[str, list[str]], classification: str) -> None:
    payload = {
        "added": diff["added"],
        "removed": diff["removed"],
        "modified": diff["modified"],
        "breaking": classification == "major",
        "classification": classification,
    }
    SCHEMA_DIFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_DIFF_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_golden_hash(name: str) -> str:
    path = GOLDEN_DIR / f"{name}.json"
    if not path.exists():
        return "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "invalid"
    return str(data.get("hash", "unset"))


def _write_changelog(diff: Dict[str, list[str]], classification: str) -> None:
    CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = ["# Offline API Changelog", ""]
    content.append(f"- Generated: {datetime.utcnow().isoformat()}Z")
    content.append(f"- Classification: {classification}")
    content.append(f"- Added endpoints: {', '.join(diff['added']) or 'none'}")
    content.append(f"- Removed endpoints: {', '.join(diff['removed']) or 'none'}")
    content.append(f"- Modified endpoints: {', '.join(diff['modified']) or 'none'}")
    content.append(f"- Golden /predict hash: `{_load_golden_hash('predict')}`")
    content.append(f"- Golden stream hash: `{_load_golden_hash('stream')}`")
    CHANGELOG_PATH.write_text("\n".join(content) + "\n", encoding="utf-8")


def _load_current_spec() -> Dict[str, object]:
    if not CURRENT_PATH.exists():
        raise SystemExit(
            "current OpenAPI spec missing; run scripts/openapi_export.py before diff"
        )
    try:
        return json.loads(CURRENT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid OpenAPI json at {CURRENT_PATH}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare generated OpenAPI schema against baseline")
    parser.add_argument("--approve", action="store_true", help="Refresh the baseline with the current schema")
    args = parser.parse_args()

    spec = _load_current_spec()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
        _write_diff({"added": [], "removed": [], "modified": []}, "patch")
        _write_changelog({"added": [], "removed": [], "modified": []}, "patch")
        print("baseline created")
        return

    baseline_spec = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline_ops = _canonical_operations(baseline_spec)
    current_ops = _canonical_operations(spec)
    diff = _classify_diff(baseline_ops, current_ops)
    classification = _classification(diff)
    _write_diff(diff, classification)
    _write_changelog(diff, classification)

    if args.approve:
        BASELINE_PATH.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
        print(f"baseline updated ({classification})")
        return

    if classification == "major":
        if os.getenv("SCHEMA_BREAKING_OK", "").lower() not in {"1", "true", "yes"}:
            raise SystemExit("breaking change detected; set SCHEMA_BREAKING_OK=1 to proceed")
        _ensure_migration_note()
    elif classification == "minor":
        print("non-breaking additions detected")
    else:
        print("schema unchanged")


if __name__ == "__main__":
    main()

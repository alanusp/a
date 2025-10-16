from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path("schemas/avro")
CANONICAL_DIR = Path("artifacts/avro_canonical")


def canonical_name(schema: dict[str, Any]) -> str:
    namespace = schema.get("namespace")
    name = schema.get("name")
    if namespace:
        return f"{namespace}.{name}"
    return str(name)


def canonical_form(schema: Any) -> Any:
    if isinstance(schema, str):
        return schema
    if isinstance(schema, list):
        return [canonical_form(item) for item in schema]
    if isinstance(schema, dict):
        type_name = schema.get("type")
        if type_name == "record":
            fields = []
            for field in schema.get("fields", []):
                entry: dict[str, Any] = {"name": field["name"], "type": canonical_form(field["type"])}
                if "default" in field:
                    entry["default"] = field["default"]
                fields.append(entry)
            return {"type": "record", "name": canonical_name(schema), "fields": fields}
        return {key: canonical_form(value) for key, value in sorted(schema.items())}
    return schema


def canonical_string(schema: Any) -> str:
    return json.dumps(canonical_form(schema), separators=(",", ":"), sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Avro canonical forms")
    parser.add_argument("--update", action="store_true", help="refresh canonical baselines")
    args = parser.parse_args()

    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    failures = []

    for schema_path in sorted(SCHEMA_DIR.glob("*.avsc")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        canonical = canonical_string(schema)
        target = CANONICAL_DIR / f"{schema_path.stem}.txt"
        if args.update or not target.exists():
            target.write_text(canonical + "\n", encoding="utf-8")
            continue
        if target.read_text(encoding="utf-8").strip() != canonical:
            failures.append(schema_path.name)

    if failures:
        print("Canonical form mismatch for:", ", ".join(failures))
        print("Run `python scripts/avro_canonical_gate.py --update` to refresh baselines.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

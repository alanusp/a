from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.json_canonical import canonicalize


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    artifacts = Path("artifacts")
    state = load_state(artifacts / "migration_state.json")
    parity = load_state(artifacts / "parity_report.json")
    report = {
        "state": state.get("phase", "unknown"),
        "parity": parity.get("match_rate", 1.0),
        "rollback_ready": state.get("phase") in {"monitor", "finalize", "committed"},
    }
    output = artifacts / "rollback_report.json"
    output.write_text(canonicalize(report), encoding="utf-8")
    print(f"rollback rehearsal report written to {output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

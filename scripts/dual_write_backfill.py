"""Offline backfill utility for dual-write migrations.

Reads scored events from a baseline JSONL file and replays them into the
candidate version by invoking the migration service parity tracker. The script
is idempotent: it records the last processed offset alongside the output file so
it can resume after interruptions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

from app.core.config import get_settings
from streaming.pipeline import build_dual_write_records


def _default_input() -> Path:
    return Path("artifacts/golden/stream.json")


def _resume_token_path(output: Path) -> Path:
    return output.with_suffix(".offset")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dual-write backfill utility")
    parser.add_argument("--input", type=Path, default=_default_input(), help="Baseline JSON payloads")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/migration_backfill.jsonl"),
        help="Where to store candidate records",
    )
    args = parser.parse_args()
    settings = get_settings()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    resume_token = 0
    token_path = _resume_token_path(args.output)
    if token_path.exists():
        try:
            resume_token = int(token_path.read_text().strip())
        except ValueError:
            resume_token = 0
    with args.input.open("r", encoding="utf-8") as infile, args.output.open(
        "a", encoding="utf-8"
    ) as outfile:
        for idx, line in enumerate(infile):
            if idx < resume_token:
                continue
            payload: Dict[str, object] = json.loads(line)
            if "event_id" not in payload:
                continue
            payload.setdefault("idempotency_key", payload["event_id"])
            records = build_dual_write_records(payload)
            for record in records:
                if record["version"] == settings.scored_topic_next_version:
                    outfile.write(json.dumps(record) + "\n")
            token_path.write_text(str(idx + 1))
    print(f"Backfill complete for {args.output}")


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    main()

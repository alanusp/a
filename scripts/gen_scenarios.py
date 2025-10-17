from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any, Dict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback path
    yaml = None
    import json as _json

    def _safe_load(text: str) -> dict[str, object]:
        data = _json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("JSON scenario must decode to a mapping")
        return data
else:  # pragma: no cover - executed when PyYAML available
    def _safe_load(text: str) -> dict[str, object]:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("Expected mapping from YAML scenario")
        return data


def _load_scenario(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = _safe_load(handle.read())
    if not isinstance(data, dict):
        raise ValueError(f"Scenario file {path} did not produce a mapping")
    return data


def _synthesise(data: Dict[str, Any]) -> list[dict[str, Any]]:
    seed = int(data.get("seed", 0))
    volume = int(data.get("volume", 0))
    rng = Random(seed)
    start = datetime(2024, 1, 1, 0, 0, 0)
    patterns = data.get("patterns", [])
    lag_minutes = int(data.get("label_lag_minutes", 0))
    events: list[dict[str, Any]] = []
    for index in range(volume):
        timestamp = start + timedelta(minutes=index)
        event = {
            "event_id": f"{data.get('name', 'scenario')}::{index:05d}",
            "user_id": f"user_{rng.randint(1, 999):03d}",
            "merchant_id": f"merchant_{rng.randint(1, 100):03d}",
            "device_id": f"device_{rng.randint(1, 500):03d}",
            "amount": round(rng.uniform(5.0, 250.0), 2),
            "base_probability": round(rng.uniform(0.02, 0.25), 4),
            "occurred_at": timestamp.isoformat(),
        }
        probability = event["base_probability"]
        for pattern in patterns:
            ptype = pattern.get("type")
            if ptype == "burst" and index < int(pattern.get("duration", 0)):
                event["user_id"] = rng.choice(pattern.get("user_ids", [event["user_id"]]))
                event["amount"] = float(pattern.get("amount", event["amount"]))
                probability = max(probability, float(pattern.get("probability", probability)))
            elif ptype == "mule_ring":
                event["merchant_id"] = rng.choice(pattern.get("merchants", [event["merchant_id"]]))
                base = float(pattern.get("base_probability", probability))
                jitter = float(pattern.get("jitter", 0.0))
                probability = max(probability, base + rng.uniform(-jitter, jitter))
        probability = min(max(probability, 0.0), 1.0)
        label_delay = timedelta(minutes=lag_minutes + rng.randint(0, 5))
        event["label_expected_at"] = (timestamp + label_delay).isoformat()
        event["label"] = 1 if rng.random() < probability else 0
        event["probability"] = probability
        events.append(event)
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic fraud scenarios")
    parser.add_argument("--directory", default="scenarios", help="Directory containing scenario YAML files")
    parser.add_argument(
        "--output", default="artifacts/scenarios", help="Destination directory for generated JSONL files"
    )
    args = parser.parse_args()

    scenario_dir = Path(args.directory)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(scenario_dir.glob("*.yaml")):
        data = _load_scenario(path)
        events = _synthesise(data)
        output_path = output_dir / f"{path.stem}.jsonl"
        with output_path.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

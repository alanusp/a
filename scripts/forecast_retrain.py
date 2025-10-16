#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from app.services.forecast import ThresholdForecaster


def main() -> None:
    dataset_path = Path("artifacts/telemetry/prevalence.json")
    if not dataset_path.exists():
        raise SystemExit("telemetry dataset missing; run make e2e first")
    entries = json.loads(dataset_path.read_text())
    forecaster = ThresholdForecaster()
    schedule: dict[str, list[float]] = {}
    for record in entries:
        result = forecaster.update(record["segment"], int(record["index"]), float(record["prevalence"]))
        schedule.setdefault(record["segment"], []).append(result["recommended_threshold"])
    output = Path("artifacts/forecast_schedule.json")
    output.write_text(json.dumps(schedule, indent=2, sort_keys=True))
    print(f"wrote {output}")


if __name__ == "__main__":
    main()

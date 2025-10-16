#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS = ROOT / "artifacts" / "perf" / "burn_metrics.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"metrics file missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(metrics: dict[str, Any], *, error_threshold: float, latency_threshold: float) -> tuple[bool, list[str]]:
    windows: Iterable[dict[str, Any]] = metrics.get("windows", [])
    failures: list[str] = []
    for window in windows:
        duration = float(window.get("duration_minutes", 0.0))
        slo_window = float(window.get("slo_window_minutes", duration or 60.0))
        multiplier = duration / slo_window if slo_window else 1.0
        error_rate = float(window.get("error_rate", 0.0))
        error_slo = float(window.get("slo_error", 0.001))
        latency = float(window.get("latency_p95", 0.0))
        latency_slo = float(window.get("latency_slo", 1.0))
        error_burn = multiplier * (error_rate / max(error_slo, 1e-9))
        latency_burn = multiplier * (latency / max(latency_slo, 1e-9))
        window_name = window.get("name") or f"{int(duration)}m"
        if error_burn > error_threshold:
            failures.append(f"{window_name} error burn {error_burn:.2f} > {error_threshold}")
        if latency_burn > latency_threshold:
            failures.append(f"{window_name} latency burn {latency_burn:.2f} > {latency_threshold}")
    return (len(failures) == 0, failures)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce burn-rate gates using persisted metrics")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--error-threshold", type=float, default=2.0)
    parser.add_argument("--latency-threshold", type=float, default=2.0)
    args = parser.parse_args()

    metrics = _load(args.metrics)
    passed, failures = evaluate(metrics, error_threshold=args.error_threshold, latency_threshold=args.latency_threshold)
    report_path = args.metrics.parent / "burn_report.json"
    report_path.write_text(
        json.dumps({"passed": passed, "failures": failures}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if not passed:
        for failure in failures:
            print(failure)
        raise SystemExit(1)
    print("burn-rate gate passed")


if __name__ == "__main__":
    main()

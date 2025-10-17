#!/usr/bin/env python3
from __future__ import annotations

import json
import random
from pathlib import Path

QUANTILES = [0.95, 0.99]
ITERATIONS = 500
ALPHA = 0.05


def _load_samples(path: Path) -> list[float]:
    if not path.exists():
        raise SystemExit(f"missing latency samples: {path}")
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and "latencies" in payload:
        return [float(value) for value in payload["latencies"]]
    if isinstance(payload, dict):
        samples: list[float] = []
        for bucket, count in payload.items():
            samples.extend([float(bucket)] * int(count))
        return samples
    if isinstance(payload, list):
        return [float(value) for value in payload]
    raise SystemExit(f"unsupported payload in {path}")


def _percentile(samples: list[float], quantile: float) -> float:
    ordered = sorted(samples)
    index = int(round((len(ordered) - 1) * quantile))
    return ordered[index]


def _bootstrap_ci(samples: list[float], quantile: float) -> tuple[float, float]:
    stats: list[float] = []
    for _ in range(ITERATIONS):
        resample = [random.choice(samples) for _ in samples]
        stats.append(_percentile(resample, quantile))
    stats.sort()
    lower_idx = int((ALPHA / 2) * len(stats))
    upper_idx = int((1 - ALPHA / 2) * len(stats))
    return stats[lower_idx], stats[max(upper_idx - 1, lower_idx)]


def main() -> None:
    baseline = _load_samples(Path("artifacts/perf/baseline.json"))
    latest_path = Path("artifacts/perf/latest.json")
    latest = _load_samples(latest_path)
    report = {}
    for quantile in QUANTILES:
        base_ci = _bootstrap_ci(baseline, quantile)
        latest_ci = _bootstrap_ci(latest, quantile)
        regression = latest_ci[0] - base_ci[1]
        report[f"p{int(quantile*100)}"] = {
            "baseline_ci": base_ci,
            "latest_ci": latest_ci,
            "regression_ms": regression,
            "regressed": regression > 5.0,
        }
    report_path = Path("artifacts/perf/slo_report.json")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    if any(section["regressed"] for section in report.values()):
        raise SystemExit("SLO regression detected")
    print(f"SLO gate passed; report at {report_path}")


if __name__ == "__main__":
    main()

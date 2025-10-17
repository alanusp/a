#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from app.services.hdr import LatencyHistogram, compare_histograms, load_histogram


def main() -> None:
    run_path = Path("artifacts/perf/latest.json")
    if not run_path.exists():
        raise SystemExit("missing latest histogram; run make k6 first")
    histogram = LatencyHistogram.from_json(run_path.read_text())
    baseline_path = Path("artifacts/perf/baseline.json")
    baseline = load_histogram(baseline_path)
    result = compare_histograms(histogram, baseline, p95_budget=10.0)
    report_path = Path("artifacts/perf/hdr_report.json")
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    if result["regression_flag"]:
        raise SystemExit("p95 regression detected")
    print(f"HDR comparison passed; report at {report_path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from pathlib import Path

from app.services.perf_gate import PerformanceGate


def load_candidate(path: Path) -> list[float]:
    if not path.exists():
        raise FileNotFoundError(f"candidate samples missing at {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "latencies" in payload:
        payload = payload["latencies"]
    return [float(value) for value in payload]


def main() -> int:
    gate = PerformanceGate()
    report_dir = gate.baseline_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = report_dir / "candidate.json"
    samples = load_candidate(candidate_path)
    outcome = gate.compare(samples)
    report_path = report_dir / "report.md"
    report_path.write_text(
        "\n".join(
            [
                "# Performance Regression Report",
                f"Baseline samples: {int(outcome['baseline_count'])}",
                f"Candidate samples: {int(outcome['candidate_count'])}",
                f"KS statistic: {outcome['statistic']:.6f}",
                f"Critical value: {outcome['critical']:.6f}",
                f"Regression detected: {outcome['regression']}",
            ]
        ),
        encoding="utf-8",
    )
    if outcome["regression"]:
        raise SystemExit("latency regression detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

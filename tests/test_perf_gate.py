from __future__ import annotations

import json

from app.services.perf_gate import PerformanceGate


def test_performance_gate_detects_regression(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps({"latencies": [40, 42, 41, 39, 40]}), encoding="utf-8")
    gate = PerformanceGate(baseline_path=baseline_path)

    healthy = gate.compare([40, 41, 42, 39, 40])
    assert healthy["regression"] is False

    degraded = gate.compare([80, 82, 78, 81, 79])
    assert degraded["regression"] is True

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.diagnostics import build_bundle
from app.services.model_guard import ModelGuard
from scripts.import_hygiene import analyze
from scripts.burn_rate_gate import evaluate as evaluate_burn


def test_import_hygiene_clean() -> None:
    report = analyze()
    assert report["orphans"] == []
    assert report["cycles"] == []
    assert report["heavy"] == []


def test_model_guard_similarity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = Path("artifacts/model_state_dict.json")
    candidate = tmp_path / "candidate.json"
    candidate.write_text(baseline.read_text(encoding="utf-8"), encoding="utf-8")
    cal_candidate = tmp_path / "calibration.json"
    cal_baseline = Path("artifacts/calibration.json")
    if cal_baseline.exists():
        cal_candidate.write_text(cal_baseline.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        cal_candidate.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("MODEL_CANDIDATE_PATH", str(candidate))
    monkeypatch.setenv("CALIBRATION_CANDIDATE_PATH", str(cal_candidate))
    monkeypatch.setenv("MODEL_DRIFT_THRESHOLD", "0.95")
    get_settings.cache_clear()
    try:
        guard = ModelGuard()
        report = guard.evaluate()
    finally:
        get_settings.cache_clear()
    assert report.within_bounds


def test_diag_bundle_creation() -> None:
    bundle = build_bundle(None)
    assert bundle.exists()


def test_burn_rate_gate_pass_and_fail() -> None:
    metrics = {
        "windows": [
            {
                "name": "1h",
                "duration_minutes": 60,
                "slo_window_minutes": 1440,
                "error_rate": 0.001,
                "slo_error": 0.01,
                "latency_p95": 120,
                "latency_slo": 150,
            },
            {
                "name": "6h",
                "duration_minutes": 360,
                "slo_window_minutes": 1440,
                "error_rate": 0.0005,
                "slo_error": 0.01,
                "latency_p95": 110,
                "latency_slo": 150,
            },
        ]
    }
    passed, failures = evaluate_burn(metrics, error_threshold=2.0, latency_threshold=2.0)
    assert passed
    assert failures == []

    metrics["windows"][0]["error_rate"] = 0.5
    passed, failures = evaluate_burn(metrics, error_threshold=2.0, latency_threshold=2.0)
    assert not passed
    assert failures

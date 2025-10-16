from __future__ import annotations

from app.services.hdr import LatencyHistogram, compare_histograms


def test_histogram_percentiles_and_regression_flag() -> None:
    baseline = LatencyHistogram()
    latest = LatencyHistogram()
    for value in [40, 42, 45, 47, 50]:
        baseline.record(value)
    for value in [40, 42, 45, 90, 95]:
        latest.record(value)
    report = compare_histograms(latest, baseline, p95_budget=60.0)
    assert report["regression_flag"] == 0.0
    report = compare_histograms(latest, baseline, p95_budget=5.0)
    assert report["regression_flag"] == 1.0

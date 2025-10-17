from __future__ import annotations

from app.services.forecast import ThresholdForecaster


def test_forecast_reduces_cost_against_static() -> None:
    forecaster = ThresholdForecaster(alpha=0.5)
    static_cost = 0.0
    adaptive_cost = 0.0
    for idx in range(24):
        prevalence = 0.1 if idx < 12 else 0.3
        static_threshold = 0.2
        static_cost += abs(prevalence - static_threshold)
        schedule = forecaster.update("segment-a", idx, prevalence)
        adaptive_cost += abs(prevalence - schedule["recommended_threshold"])
    assert adaptive_cost <= static_cost

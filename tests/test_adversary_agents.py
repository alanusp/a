from __future__ import annotations

from adversary.agents.base import evaluate_agents


def test_adversary_agents_recovery_improves_with_deflection():
    aggressive = evaluate_agents(deflection_rate=0.1)
    resilient = evaluate_agents(deflection_rate=0.7)

    for name, outcome in aggressive.items():
        harder = resilient[name]
        assert harder.success_rate <= outcome.success_rate
        assert harder.recovery_time <= outcome.recovery_time

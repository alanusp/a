from __future__ import annotations

import asyncio

from app.services.canary import (
    CanaryOrchestrator,
    CanaryThresholds,
    InMemoryModelConfigStore,
    ModelPerformance,
)
from app.services.shadow import InMemoryShadowRepository, ShadowTrafficService


def test_shadow_records_are_persisted():
    repo = InMemoryShadowRepository(maxlen=10)
    service = ShadowTrafficService(repository=repo)
    headers = {"X-Shadow": "true", "X-Model-Version": "v2"}
    import asyncio

    asyncio.run(
        service.record(
            headers=headers,
            transaction_id="txn-1",
            features=[0.1, 0.2],
            probability=0.42,
            latency_ms=12.0,
            trace_context={"trace_id": "abc"},
        )
    )
    records = repo.latest()
    assert len(records) == 1
    assert records[0].model_version == "v2"


def test_canary_guardrails_trigger_rollback():
    store = InMemoryModelConfigStore(initial_version="baseline")
    thresholds = CanaryThresholds(max_latency_delta_pct=5.0)
    orchestrator = CanaryOrchestrator(thresholds=thresholds, config_store=store)
    baseline = ModelPerformance(auroc=0.92, aupr=0.75, p95_latency_ms=80, alert_rate=0.02)
    candidate = ModelPerformance(auroc=0.93, aupr=0.76, p95_latency_ms=100, alert_rate=0.025)

    decision = orchestrator.evaluate(
        candidate_version="model-v2",
        candidate=candidate,
        baseline_version="model-v1",
        baseline=baseline,
    )
    assert decision.accepted is False
    orchestrator.apply(decision)
    assert store.get_active_model() == "model-v1"

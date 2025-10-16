from __future__ import annotations

import json

from app.core.trace import event_identifier, propagate_headers, start_trace
from app.services.lineage import LineageEmitter
from scripts.clock_drift_check import run_check


def test_event_identifier_and_lamport(tmp_path):
    first = start_trace({})
    second = start_trace(propagate_headers(first))
    assert second.lamport > first.lamport
    event_id = event_identifier(second, tenant_id="tenant", transaction_id="abc")
    assert event_id.startswith("tenant-")
    assert event_id.count("-") == 3


def test_lineage_emitter_writes_json(tmp_path):
    emitter = LineageEmitter(directory=tmp_path)
    context = start_trace({})
    path = emitter.emit(
        name="inference",
        context=context,
        inputs=[{"name": "input"}],
        outputs=[{"name": "output"}],
        facets=emitter.run_facets({"latency_ms": 42}),
    )
    content = path.read_text(encoding="utf-8").strip().splitlines()
    assert content
    record = json.loads(content[-1])
    assert record["job"]["name"] == "inference"
    assert record["run"]["runId"].startswith(context.trace_id)


def test_clock_drift_guard() -> None:
    assert run_check()
    assert not run_check(simulated_offset=0.5, tolerance=0.05)

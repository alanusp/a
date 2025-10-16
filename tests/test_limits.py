from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings
from app.core.limits import reset_limit_registry, severity_score
from graph.engine import GraphEngine
from app.services.sketch_book import SketchBook


def _reset_limits() -> None:
    reset_limit_registry()
    get_settings.cache_clear()


def test_graph_limit_shed(monkeypatch) -> None:
    monkeypatch.setenv("GRAPH_NODE_SOFT_CAP", "2")
    monkeypatch.setenv("GRAPH_NODE_HARD_CAP", "2")
    monkeypatch.setenv("GRAPH_EDGE_SOFT_CAP", "1")
    monkeypatch.setenv("GRAPH_EDGE_HARD_CAP", "1")
    _reset_limits()
    engine = GraphEngine()
    engine.ingest(
        event_id="evt-1",
        timestamp=datetime.utcnow(),
        relationships={"customer_id": "c1", "merchant_id": "m1"},
        fraud_probability=0.1,
    )
    assert engine.limit_state in {"ok", "soft"}
    engine.ingest(
        event_id="evt-2",
        timestamp=datetime.utcnow(),
        relationships={"customer_id": "c2", "merchant_id": "m2", "device_id": "d2"},
        fraud_probability=0.9,
    )
    assert engine.limit_state == "hard"
    assert "evt-2" not in engine._snapshots  # type: ignore[attr-defined]


def test_sketch_limit_metrics(monkeypatch) -> None:
    monkeypatch.setenv("SKETCH_CARDINALITY_SOFT_CAP", "1")
    monkeypatch.setenv("SKETCH_CARDINALITY_HARD_CAP", "1")
    _reset_limits()
    book = SketchBook(width=16, depth=3, bloom_capacity=32, bloom_hashes=2)
    metrics = book.observe("evt-1", customer_id="c1", device_id="d1", merchant_id="m1")
    assert metrics["sketch_limit_severity"] == severity_score("ok")
    metrics = book.observe("evt-2", customer_id="c2", device_id="d2", merchant_id="m2")
    assert metrics["sketch_limit_severity"] == severity_score("hard")

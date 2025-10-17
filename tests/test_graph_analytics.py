from __future__ import annotations

from graph.centrality import ego_betweenness
from graph.engine import GraphEngine
from graph.ppr import local_push_ppr


def _build_small_graph() -> GraphEngine:
    engine = GraphEngine()
    engine.ingest(
        event_id="e1",
        timestamp=datetime.utcnow(),
        relationships={"customer_id": "c1", "device_id": "d1", "merchant_id": "m1"},
        fraud_probability=0.1,
    )
    engine.ingest(
        event_id="e2",
        timestamp=datetime.utcnow(),
        relationships={"customer_id": "c2", "device_id": "d1", "merchant_id": "m2"},
        fraud_probability=0.3,
    )
    engine.ingest(
        event_id="e3",
        timestamp=datetime.utcnow(),
        relationships={"customer_id": "c3", "device_id": "d2", "merchant_id": "m1"},
        fraud_probability=0.8,
    )
    return engine


from datetime import datetime


def test_local_push_pagerank_focus() -> None:
    engine = _build_small_graph()
    adjacency = engine._adjacency_view()  # type: ignore[attr-defined]
    node = "customer:c1"
    result = local_push_ppr(adjacency, node, alpha=0.7, tolerance=1e-4)
    assert result[node] > 0.2
    assert abs(sum(result.values()) - 1.0) < 1e-6


def test_ego_betweenness_increases_with_edges() -> None:
    engine = _build_small_graph()
    adjacency = engine._adjacency_view()  # type: ignore[attr-defined]
    node = "device:d1"
    baseline = ego_betweenness(adjacency, node)
    engine.ingest(
        event_id="e4",
        timestamp=datetime.utcnow(),
        relationships={"customer_id": "c4", "device_id": "d1", "merchant_id": "m3"},
        fraud_probability=0.2,
    )
    adjacency = engine._adjacency_view()  # type: ignore[attr-defined]
    assert ego_betweenness(adjacency, node) >= baseline

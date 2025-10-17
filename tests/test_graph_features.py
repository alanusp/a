from __future__ import annotations

from datetime import datetime

from graph.engine import GraphEngine


def test_graph_metrics_progression() -> None:
    engine = GraphEngine()
    engine.ingest(
        event_id="evt-1",
        timestamp=datetime.utcnow(),
        relationships={
            "customer_id": "cust-1",
            "device_id": "dev-1",
            "merchant_id": "m-1",
        },
        fraud_probability=0.9,
    )
    metrics = engine.compute_metrics(
        {
            "customer_id": "cust-1",
            "device_id": "dev-1",
            "merchant_id": "m-1",
        }
    )
    assert metrics["customer_degree"] >= 1
    assert metrics["merchant_degree"] >= 1
    assert metrics["neighbour_risk"] > 0

    engine.ingest(
        event_id="evt-2",
        timestamp=datetime.utcnow(),
        relationships={
            "customer_id": "cust-2",
            "device_id": "dev-1",
            "merchant_id": "m-2",
        },
        fraud_probability=0.2,
    )
    metrics = engine.compute_metrics({"customer_id": "cust-2", "device_id": "dev-1"})
    assert metrics["shared_device_customers"] >= 1
    assert engine.shortest_path_length("customer:cust-1", "merchant:m-2") <= 3

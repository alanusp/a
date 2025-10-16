from __future__ import annotations

from datetime import datetime, timedelta

from app.core.bitemporal import BitemporalStore


def test_bitemporal_query_as_of() -> None:
    store = BitemporalStore()
    first_insert_time = datetime.utcnow()
    store.upsert("customer:c1", {"score": 0.1}, valid_from=first_insert_time - timedelta(days=2))
    second_insert_time = datetime.utcnow()
    store.upsert("customer:c1", {"score": 0.4}, valid_from=first_insert_time - timedelta(days=1))
    value = store.query_as_of(
        "customer:c1",
        valid_time=first_insert_time - timedelta(days=1, minutes=1),
        system_time=second_insert_time - timedelta(microseconds=1),
    )
    assert value == {"score": 0.1}
    current_time = datetime.utcnow()
    value = store.query_as_of("customer:c1", valid_time=current_time, system_time=current_time)
    assert value == {"score": 0.4}

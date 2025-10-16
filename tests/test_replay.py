from __future__ import annotations

from datetime import datetime, timedelta

from app.services.replay import InMemoryReplayStore, ReplayRecord, ReplayService


def test_replay_round_trip_is_deterministic():
    store = InMemoryReplayStore()
    service = ReplayService(store)
    now = datetime.utcnow()
    records = [
        ReplayRecord(
            transaction_id="t-1",
            occurred_at=now - timedelta(seconds=2),
            probability=0.4,
            model_hash="model-a",
            features=[0.1, 0.2],
        ),
        ReplayRecord(
            transaction_id="t-2",
            occurred_at=now - timedelta(seconds=1),
            probability=0.7,
            model_hash="model-a",
            features=[0.3, 0.4],
        ),
    ]
    determinism_hash = service.archive_batch(records)
    replayed = service.replay_window(start=now - timedelta(seconds=5), end=now)
    assert replayed["determinism_hash"] == determinism_hash
    assert len(replayed["records"]) == 2

    filtered = service.replay_window(
        start=now - timedelta(seconds=5),
        end=now,
        model_hash="model-a",
    )
    assert filtered["determinism_hash"] == determinism_hash

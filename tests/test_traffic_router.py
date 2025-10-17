from __future__ import annotations

import json

from app.core.flags import FeatureFlagSet
from app.services.traffic_router import TrafficRouter


class DummySettings:
    candidate_traffic_percent = 0.0


def test_router_respects_candidate_percentage(tmp_path) -> None:
    flags_dir = tmp_path / "flags"
    flags_dir.mkdir()
    (flags_dir / "routing.json").write_text(json.dumps({"traffic.candidate_pct": 50}))
    router = TrafficRouter(flags=FeatureFlagSet(flags_dir), settings=DummySettings())
    sample = [router.select(tenant_id="tenant", event_id=f"event-{idx}") for idx in range(100)]
    candidate = sum(1 for item in sample if item == "candidate")
    assert 20 <= candidate <= 80  # sticky but roughly distributed
    router.override_to_baseline()
    snap = router.snapshot(safe_mode=False)
    assert snap.candidate >= 0.0
    assert snap.baseline <= 1.0


def test_router_forces_safe_mode(tmp_path) -> None:
    router = TrafficRouter(flags=FeatureFlagSet(tmp_path), settings=DummySettings())
    route = router.select(tenant_id="tenant", event_id="evt-1", safe_mode=True)
    assert route == "baseline"
    snap = router.snapshot(safe_mode=True)
    assert snap.safe_mode is True

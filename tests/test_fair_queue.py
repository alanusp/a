from __future__ import annotations

from app.services.sla import SLAScheduler


def test_drr_fairness() -> None:
    scheduler = SLAScheduler()
    allowed = sum(1 for _ in range(3) if scheduler.admit("tenant-a").allowed)
    assert allowed == 3
    denied = scheduler.admit("tenant-a")
    assert not denied.allowed
    retry = scheduler.admit("tenant-b")
    assert retry.allowed

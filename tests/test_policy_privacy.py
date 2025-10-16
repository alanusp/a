from datetime import datetime, timedelta
from pathlib import Path

from app.services.policy import PolicyService
from app.services.privacy import PrivacyService


def test_policy_rules_apply(tmp_path):
    rules_path = Path("rules")
    service = PolicyService(rules_path=rules_path)
    decision = service.decide(
        probability=0.2,
        context={"amount": 9000, "velocity": 6, "probability": 0.2},
        threshold_action="approve",
    )
    assert decision.action in {"block", "review"}
    assert decision.matched_rules


def test_privacy_hashing_rotation(tmp_path):
    salt_path = tmp_path / "salt.key"
    privacy = PrivacyService(salt_path=salt_path, retention_days=1)
    digest_one = privacy.hash_value("alice@example.com")
    digest_two = privacy.hash_value("alice@example.com")
    assert digest_one == digest_two
    privacy.rotate_salt()
    digest_three = privacy.hash_value("alice@example.com")
    assert digest_three != digest_one
    records = [
        {"observed_at": datetime.utcnow() - timedelta(days=2)},
        {"observed_at": datetime.utcnow()},
    ]
    pruned = privacy.purge_before(privacy.retention_cutoff(), records, field="observed_at")
    assert len(pruned) == 1

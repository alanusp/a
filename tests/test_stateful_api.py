from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

try:
    from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, precondition, rule
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    Bundle = RuleBasedStateMachine = invariant = precondition = rule = None  # type: ignore

from app.core.config import get_settings
from app.core.startup import reset_startup_state
from app.services.decision import DecisionService
from app.services.dsar_ops import DSAROperator
from app.services.feature_service import FeatureService
from app.services.feedback import FeedbackService
from app.services.inference_service import InferenceService
from app.services.replay import ReplayRecord, ReplayService


def _sample_payload(seq: int) -> dict[str, object]:
    return {
        "transaction_id": f"txn-{seq}",
        "customer_id": f"cust-{seq % 3}",
        "merchant_id": "merchant-1",
        "device_id": f"device-{seq % 2}",
        "card_id": f"card-{seq % 5}",
        "ip_address": "1.1.1.1",
        "amount": 12.5 + seq,
        "currency": "USD",
        "device_trust_score": 0.5,
        "merchant_risk_score": 0.3,
        "velocity_1m": 1.0,
        "velocity_1h": 2.0,
        "chargeback_rate": 0.1,
        "account_age_days": 100.0,
        "customer_tenure": 200.0,
        "geo_distance": 10.0,
        "segment": "public",
    }


if RuleBasedStateMachine is not None:

    class FraudWorkflowMachine(RuleBasedStateMachine):
        Events = Bundle("events")

        def __init__(self) -> None:
            super().__init__()
            self.tmpdir = Path("artifacts/stateful")
            if self.tmpdir.exists():
                shutil.rmtree(self.tmpdir)
            self.tmpdir.mkdir(parents=True, exist_ok=True)
            os.environ["FEEDBACK_STORE_PATH"] = str(self.tmpdir / "feedback.jsonl")
            os.environ["AUDIT_LEDGER_PATH"] = str(self.tmpdir / "ledger.jsonl")
            os.environ["AUDIT_ANCHOR_PATH"] = str(self.tmpdir / "anchor.json")
            get_settings.cache_clear()
            reset_startup_state()
            self.feature_service = FeatureService()
            self.inference_service = InferenceService()
            self.feedback_service = FeedbackService()
            self.replay_service = ReplayService()
            self.decision_service = DecisionService()
            self.dsar = DSAROperator(salt="stateful")
            self._sequence = 0
            self._events: Dict[str, float] = {}

        @rule(target=Events)
        def predict(self):
            self._sequence += 1
            payload = _sample_payload(self._sequence)
            features = self.feature_service.to_feature_list(payload)
            result = self.inference_service.predict(features)
            event_id = self.feedback_service.register_prediction(
                event_id=payload["transaction_id"],
                features=features,
                probability=result.probability,
                occurred_at=datetime.now(timezone.utc),
                group=payload.get("segment"),
                tenant_id="public",
            )
            self.replay_service.archive_batch(
                [
                    ReplayRecord(
                        transaction_id=payload["transaction_id"],
                        occurred_at=datetime.now(timezone.utc),
                        probability=result.probability,
                        model_hash="mhash",
                        features=list(features),
                    )
                ]
            )
            self._events[event_id] = result.probability
            return event_id

        @precondition(lambda self: bool(self._events))
        @rule(event=Events)
        def feedback(self, event: str) -> None:
            outcome = self.feedback_service.record_feedback(
                event_id=event,
                label=1.0,
                observed_at=datetime.now(timezone.utc),
                group="public",
                tenant_id="public",
            )
            assert outcome.label == 1.0

        @precondition(lambda self: bool(self._events))
        @rule(event=Events)
        def decide(self, event: str) -> None:
            payload = _sample_payload(self._sequence)
            payload["transaction_id"] = event
            response = self.decision_service.decide(payload, tenant_id="public")
            assert response.action in {"allow", "review", "deny"}

        @precondition(lambda self: bool(self._events))
        @rule(event=Events)
        def dsar_delete(self, event: str) -> None:
            record = self.dsar.delete({"event_id": event})
            assert record["event_id"] == event

        @invariant()
        def audit_is_append_only(self) -> None:
            ledger_path = Path(os.getenv("AUDIT_LEDGER_PATH"))
            if ledger_path.exists():
                lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
                indexes = [json.loads(line)["index"] for line in lines if line]
                assert indexes == sorted(indexes)

    TestWorkflow = FraudWorkflowMachine.TestCase

else:

    def test_stateful_workflow_skipped():
        import pytest

        pytest.skip("hypothesis unavailable")

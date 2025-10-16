from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

from app.core.config import get_settings


@dataclass(slots=True)
class PredictionRecord:
    event_id: str
    features: list[float]
    probability: float
    occurred_at: datetime
    group: str | None
    tenant_id: str

    def serialise(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "features": self.features,
            "probability": self.probability,
            "occurred_at": self.occurred_at.isoformat(),
            "group": self.group,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "PredictionRecord":
        return cls(
            event_id=str(payload["event_id"]),
            features=[float(value) for value in payload.get("features", [])],
            probability=float(payload.get("probability", 0.0)),
            occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
            group=payload.get("group") if payload.get("group") is not None else None,
            tenant_id=str(payload.get("tenant_id", "public")),
        )


@dataclass(slots=True)
class FeedbackRecord:
    event_id: str
    label: float
    observed_at: datetime
    delay_seconds: float
    group: str | None
    tenant_id: str

    def serialise(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "label": self.label,
            "observed_at": self.observed_at.isoformat(),
            "delay_seconds": self.delay_seconds,
            "group": self.group,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "FeedbackRecord":
        return cls(
            event_id=str(payload["event_id"]),
            label=float(payload.get("label", 0.0)),
            observed_at=datetime.fromisoformat(str(payload["observed_at"])),
            delay_seconds=float(payload.get("delay_seconds", 0.0)),
            group=payload.get("group") if payload.get("group") is not None else None,
            tenant_id=str(payload.get("tenant_id", "public")),
        )


@dataclass(slots=True)
class FeedbackJoinResult:
    applied: bool
    sample_weight: float
    delay_seconds: float
    features: Optional[list[float]]
    probability: Optional[float]
    group: str | None
    label: float
    tenant_id: str


class FeedbackService:
    """Persist predictions and ingest delayed feedback for online learning."""

    def __init__(self, store_path: Path | None = None) -> None:
        settings = get_settings()
        self.store_path = store_path or settings.feedback_store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._predictions: Dict[str, PredictionRecord] = {}
        self._feedback: Dict[str, FeedbackRecord] = {}
        self._load()

    def register_prediction(
        self,
        *,
        event_id: str,
        features: Iterable[float],
        probability: float,
        occurred_at: datetime,
        group: str | None,
        tenant_id: str,
    ) -> str:
        qualified = self._qualify(event_id, tenant_id)
        record = PredictionRecord(
            event_id=qualified,
            features=[float(value) for value in features],
            probability=float(probability),
            occurred_at=occurred_at,
            group=group,
            tenant_id=tenant_id,
        )
        self._predictions[qualified] = record
        self._persist()
        return event_id

    def record_feedback(
        self,
        *,
        event_id: str,
        label: float,
        observed_at: datetime,
        group: str | None,
        tenant_id: str,
    ) -> FeedbackJoinResult:
        label = float(label)
        qualified = self._qualify(event_id, tenant_id)
        prediction = self._predictions.get(qualified)
        if prediction is None:
            feedback = FeedbackRecord(
                event_id=qualified,
                label=label,
                observed_at=observed_at,
                delay_seconds=0.0,
                group=group,
                tenant_id=tenant_id,
            )
            self._feedback[qualified] = feedback
            self._persist()
            return FeedbackJoinResult(
                applied=False,
                sample_weight=1.0,
                delay_seconds=0.0,
                features=None,
                probability=None,
                group=group,
                label=label,
                tenant_id=tenant_id,
            )

        delay_seconds = max(
            0.0,
            (observed_at - prediction.occurred_at).total_seconds(),
        )
        feedback = FeedbackRecord(
            event_id=qualified,
            label=label,
            observed_at=observed_at,
            delay_seconds=delay_seconds,
            group=group or prediction.group,
            tenant_id=tenant_id,
        )
        self._feedback[qualified] = feedback
        self._persist()

        sample_weight = 1.0 / (1.0 + delay_seconds / 86_400.0)
        return FeedbackJoinResult(
            applied=True,
            sample_weight=sample_weight,
            delay_seconds=delay_seconds,
            features=list(prediction.features),
            probability=prediction.probability,
            group=feedback.group,
            label=label,
            tenant_id=tenant_id,
        )

    def metrics(self, *, tenant_id: str | None = None) -> dict[str, float]:
        if not self._feedback:
            return {"labels": 0.0, "matched": 0.0, "avg_delay_seconds": 0.0}
        if tenant_id is not None:
            keys = [key for key in self._feedback if key.startswith(f"{tenant_id}:")]
        else:
            keys = list(self._feedback.keys())
        if not keys:
            return {"labels": 0.0, "matched": 0.0, "avg_delay_seconds": 0.0}
        matched = sum(1 for key in keys if key in self._predictions)
        avg_delay = sum(self._feedback[key].delay_seconds for key in keys) / len(keys)
        return {
            "labels": float(len(keys)),
            "matched": float(matched),
            "avg_delay_seconds": float(avg_delay),
        }

    def _persist(self) -> None:
        payload = {
            "predictions": [record.serialise() for record in self._predictions.values()],
            "feedback": [record.serialise() for record in self._feedback.values()],
        }
        self.store_path.write_text(json.dumps(payload, sort_keys=True))

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            payload = json.loads(self.store_path.read_text())
        except json.JSONDecodeError:
            return
        for record in payload.get("predictions", []):
            try:
                prediction = PredictionRecord.from_payload(record)
            except (KeyError, ValueError):
                continue
            self._predictions[prediction.event_id] = prediction
        for record in payload.get("feedback", []):
            try:
                feedback = FeedbackRecord.from_payload(record)
            except (KeyError, ValueError):
                continue
            self._feedback[feedback.event_id] = feedback

    def _qualify(self, event_id: str, tenant_id: str) -> str:
        return f"{tenant_id}:{event_id}"

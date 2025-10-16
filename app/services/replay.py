from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Protocol


@dataclass(slots=True)
class ReplayRecord:
    transaction_id: str
    occurred_at: datetime
    probability: float
    model_hash: str
    features: list[float]
    dedupe_hit: bool = False

    def serialise(self) -> dict[str, str | float | bool]:
        return {
            "transaction_id": self.transaction_id,
            "occurred_at": self.occurred_at.isoformat(),
            "probability": self.probability,
            "model_hash": self.model_hash,
            "features": self.features,
            "dedupe_hit": self.dedupe_hit,
        }


class ReplayStore(Protocol):
    def write(self, records: Iterable[ReplayRecord]) -> None: ...

    def read(self, start: datetime, end: datetime) -> List[ReplayRecord]: ...


class InMemoryReplayStore:
    def __init__(self) -> None:
        self._records: list[ReplayRecord] = []

    def write(self, records: Iterable[ReplayRecord]) -> None:
        self._records.extend(records)
        self._records.sort(key=lambda record: record.occurred_at)

    def read(self, start: datetime, end: datetime) -> List[ReplayRecord]:
        return [
            record
            for record in self._records
            if start <= record.occurred_at <= end
        ]


class ReplayService:
    def __init__(self, store: ReplayStore | None = None) -> None:
        self.store = store or InMemoryReplayStore()

    def archive_batch(self, records: Iterable[ReplayRecord]) -> str:
        records_list = list(records)
        if not records_list:
            return ""
        determinism_hash = self._determinism_hash(records_list)
        self.store.write(records_list)
        return determinism_hash

    def replay_window(
        self,
        *,
        start: datetime,
        end: datetime,
        model_hash: str | None = None,
    ) -> dict[str, object]:
        payload = self.store.read(start, end)
        if model_hash is not None:
            payload = [record for record in payload if record.model_hash == model_hash]
        determinism_hash = self._determinism_hash(payload)
        return {
            "records": [record.serialise() for record in payload],
            "determinism_hash": determinism_hash,
        }

    @staticmethod
    def _determinism_hash(records: Iterable[ReplayRecord]) -> str:
        serialised = [json.dumps(record.serialise(), sort_keys=True) for record in records]
        digest = hashlib.sha256()
        for item in serialised:
            digest.update(item.encode())
        return digest.hexdigest()

    @staticmethod
    def default_window(minutes: int) -> tuple[datetime, datetime]:
        end = datetime.utcnow()
        start = end - timedelta(minutes=minutes)
        return start, end

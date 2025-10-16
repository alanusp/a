from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional


@dataclass(slots=True)
class BitemporalRecord:
    key: str
    value: dict
    valid_from: datetime
    valid_to: datetime
    system_from: datetime
    system_to: datetime


class BitemporalStore:
    def __init__(self) -> None:
        self._records: Dict[str, List[BitemporalRecord]] = {}

    def upsert(self, key: str, value: dict, *, valid_from: datetime, valid_to: datetime | None = None) -> None:
        now = datetime.utcnow()
        valid_to = valid_to or datetime.max
        history = self._records.setdefault(key, [])
        if history:
            history[-1].system_to = now
        history.append(
            BitemporalRecord(
                key=key,
                value=value,
                valid_from=valid_from,
                valid_to=valid_to,
                system_from=now,
                system_to=datetime.max,
            )
        )

    def query_as_of(self, key: str, *, valid_time: datetime, system_time: datetime | None = None) -> Optional[dict]:
        system_time = system_time or datetime.utcnow()
        for record in reversed(self._records.get(key, [])):
            if record.valid_from <= valid_time <= record.valid_to and record.system_from <= system_time <= record.system_to:
                return record.value
        return None

    def drift_window(self, *, since: datetime) -> Iterable[BitemporalRecord]:
        for records in self._records.values():
            for record in records:
                if record.system_from >= since:
                    yield record

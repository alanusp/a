from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass
from hashlib import blake2b
from typing import Any, Deque, Dict, Iterable, List

from app.core.config import get_settings


@dataclass(frozen=True)
class ParityMetrics:
    total: int
    matches: int
    mismatches: int
    match_rate: float
    recent_mismatches: List[Dict[str, Any]]


class ParityTracker:
    """Track rolling parity between baseline and dual-write candidates."""

    def __init__(self, window: int | None = None) -> None:
        settings = get_settings()
        self._window = window or settings.dual_write_parity_window
        self._lock = threading.Lock()
        self._pairs: Deque[tuple[str, bool]] = deque(maxlen=self._window)
        self._latest: Dict[str, Dict[int, str]] = {}
        self._payloads: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._mismatches: Dict[str, Dict[str, Any]] = {}
        self._pending: set[str] = set()

    @staticmethod
    def _checksum(payload: Dict[str, Any]) -> str:
        filtered = {
            key: value
            for key, value in payload.items()
            if key not in {"version", "checksum"}
        }
        serialised = json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode()
        return blake2b(serialised, digest_size=16).hexdigest()

    def record(self, event_id: str, version: int, payload: Dict[str, Any]) -> str:
        checksum = self._checksum(payload)
        with self._lock:
            versions = self._latest.setdefault(event_id, {})
            versions[version] = checksum
            self._payloads.setdefault(event_id, {})[version] = payload
            if len(versions) < 2:
                self._pending.add(event_id)
                return checksum
            self._pending.discard(event_id)
            baseline_checksum = min(versions.items())[1]
            match = all(value == baseline_checksum for value in versions.values())
            self._pairs.append((event_id, match))
            if not match:
                mismatch_record = {
                    "event_id": event_id,
                    "checksums": versions.copy(),
                    "payloads": self._payloads[event_id].copy(),
                }
                self._mismatches[event_id] = mismatch_record
            else:
                self._mismatches.pop(event_id, None)
        return checksum

    def metrics(self) -> ParityMetrics:
        with self._lock:
            total = len(self._pairs)
            matches = sum(1 for _, ok in self._pairs if ok)
            mismatches = total - matches
            match_rate = matches / total if total else 1.0
            recent = list(self._mismatches.values())[-5:]
        return ParityMetrics(total, matches, mismatches, match_rate, recent)

    def reset(self) -> None:
        with self._lock:
            self._pairs.clear()
            self._latest.clear()
            self._payloads.clear()
            self._mismatches.clear()
            self._pending.clear()


class ParityService:
    def __init__(self, tracker: ParityTracker | None = None) -> None:
        self._tracker = tracker or ParityTracker()

    def record(self, event_id: str, version: int, payload: Dict[str, Any]) -> str:
        return self._tracker.record(event_id, version, payload)

    def metrics(self) -> ParityMetrics:
        return self._tracker.metrics()

    def validate(self, threshold: float) -> bool:
        metrics = self.metrics()
        return metrics.match_rate >= threshold

    def mismatches(self) -> Iterable[Dict[str, Any]]:
        return self.metrics().recent_mismatches

    def reset(self) -> None:
        self._tracker.reset()


_PARITY_SERVICE: ParityService | None = None


def get_parity_service() -> ParityService:
    global _PARITY_SERVICE
    if _PARITY_SERVICE is None:
        _PARITY_SERVICE = ParityService()
    return _PARITY_SERVICE


__all__ = ["ParityService", "get_parity_service", "ParityMetrics", "ParityTracker"]

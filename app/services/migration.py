from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.freeze import enforce_writable, freeze_status
from app.core.leadership import LeaderElector, LeaderLease, LeadershipError
from app.services.parity import ParityService, get_parity_service


class MigrationPhase(str, Enum):
    PREPARE = "prepare"
    DUAL_WRITE = "dual_write"
    BACKFILL = "backfill"
    VALIDATE = "validate"
    MONITOR = "monitor"
    FINALIZED = "finalized"


@dataclass
class MigrationState:
    phase: MigrationPhase = MigrationPhase.PREPARE
    leader_token: str | None = None
    leader_actor: str | None = None
    last_transition: float = field(default_factory=time.time)
    parity: Dict[str, Any] = field(default_factory=dict)
    rollback_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["phase"] = self.phase.value
        return payload

    @classmethod
    def from_file(cls, path: Path) -> "MigrationState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        phase = MigrationPhase(data.get("phase", MigrationPhase.PREPARE.value))
        return cls(
            phase=phase,
            leader_token=data.get("leader_token"),
            leader_actor=data.get("leader_actor"),
            last_transition=data.get("last_transition", time.time()),
            parity=data.get("parity", {}),
            rollback_count=data.get("rollback_count", 0),
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))


class MigrationService:
    def __init__(
        self,
        *,
        state_path: Optional[Path] = None,
        parity_service: Optional[ParityService] = None,
        leader: Optional[LeaderElector] = None,
        threshold: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        self._state_path = state_path or settings.migration_state_path
        self._parity = parity_service or get_parity_service()
        self._leader = leader or LeaderElector(role="migration")
        self._threshold = threshold or settings.dual_write_parity_threshold
        self._lock = Lock()
        self._state = MigrationState.from_file(self._state_path)

    # ------------------------------------------------------------------
    def record_event(self, event_id: str, version: int, payload: Dict[str, Any]) -> str:
        checksum = self._parity.record(event_id, version, payload)
        self._update_parity()
        return checksum

    def status(self) -> Dict[str, Any]:
        with self._lock:
            parity = self._parity.metrics()
            state = {
                "phase": self._state.phase.value,
                "leader_actor": self._state.leader_actor,
                "parity": {
                    "total": parity.total,
                    "matches": parity.matches,
                    "mismatches": parity.mismatches,
                    "match_rate": parity.match_rate,
                    "recent_mismatches": parity.recent_mismatches,
                },
                "rollback_count": self._state.rollback_count,
                "freeze": freeze_status().enabled,
            }
        return state

    # FSM operations ----------------------------------------------------
    def begin_dual_write(self, actor_id: str) -> MigrationPhase:
        lease = self._acquire(actor_id)
        with self._lock:
            self._ensure_mutable()
            self._parity.reset()
            self._state.phase = MigrationPhase.DUAL_WRITE
            self._state.last_transition = time.time()
            self._state.leader_actor = lease.actor_id
            self._state.leader_token = lease.token
            self._update_parity()
        return self._state.phase

    def begin_backfill(self, actor_id: str) -> MigrationPhase:
        lease = self._ensure_leader(actor_id)
        with self._lock:
            self._ensure_mutable()
            if self._state.phase not in {MigrationPhase.DUAL_WRITE, MigrationPhase.BACKFILL}:
                raise RuntimeError("backfill requires dual_write phase")
            self._state.phase = MigrationPhase.BACKFILL
            self._state.last_transition = time.time()
            self._state.write(self._state_path)
        self._leader.heartbeat(lease)
        return self._state.phase

    def mark_validate(self, actor_id: str) -> MigrationPhase:
        lease = self._ensure_leader(actor_id)
        with self._lock:
            self._ensure_mutable()
            if self._state.phase not in {MigrationPhase.BACKFILL, MigrationPhase.VALIDATE}:
                raise RuntimeError("validation requires backfill completion")
            self._state.phase = MigrationPhase.VALIDATE
            self._state.last_transition = time.time()
            self._update_parity()
            self._state.write(self._state_path)
        self._leader.heartbeat(lease)
        return self._state.phase

    def commit_cutover(self, actor_id: str) -> MigrationPhase:
        lease = self._ensure_leader(actor_id)
        with self._lock:
            self._ensure_mutable()
            if self._state.phase != MigrationPhase.VALIDATE:
                raise RuntimeError("cutover requires validate phase")
            metrics = self._parity.metrics()
            if metrics.match_rate < self._threshold:
                raise RuntimeError(
                    f"parity match rate {metrics.match_rate:.4f} below threshold {self._threshold:.4f}"
                )
            self._state.phase = MigrationPhase.MONITOR
            self._state.last_transition = time.time()
            self._update_parity()
            self._state.write(self._state_path)
        self._leader.heartbeat(lease)
        return self._state.phase

    def finalize(self, actor_id: str) -> MigrationPhase:
        lease = self._ensure_leader(actor_id)
        with self._lock:
            self._ensure_mutable()
            if self._state.phase != MigrationPhase.MONITOR:
                raise RuntimeError("finalize requires monitor phase")
            self._state.phase = MigrationPhase.FINALIZED
            self._state.last_transition = time.time()
            self._update_parity()
            self._state.write(self._state_path)
        self._leader.release(lease)
        return self._state.phase

    def rollback(self, actor_id: str) -> MigrationPhase:
        lease = self._ensure_leader(actor_id)
        with self._lock:
            self._ensure_mutable()
            self._state.phase = MigrationPhase.DUAL_WRITE
            self._state.rollback_count += 1
            self._state.last_transition = time.time()
            self._update_parity()
            self._state.write(self._state_path)
        self._leader.heartbeat(lease)
        return self._state.phase

    # Internal helpers ---------------------------------------------------
    def _acquire(self, actor_id: str) -> LeaderLease:
        with self._lock:
            return self._leader.acquire(actor_id)

    def _ensure_leader(self, actor_id: str) -> LeaderLease:
        with self._lock:
            if not self._state.leader_token or not self._state.leader_actor:
                raise LeadershipError("no leader established for migration")
            if self._state.leader_actor != actor_id:
                raise LeadershipError("actor is not the active migration leader")
            lease = LeaderLease(
                role="migration",
                actor_id=actor_id,
                token=self._state.leader_token,
                expires_at=time.time() + 1,
            )
        self._leader.assert_leader(lease)
        return lease

    def _ensure_mutable(self) -> None:
        enforce_writable({})

    def _update_parity(self) -> None:
        metrics = self._parity.metrics()
        self._state.parity = {
            "total": metrics.total,
            "matches": metrics.matches,
            "mismatches": metrics.mismatches,
            "match_rate": metrics.match_rate,
            "recent_mismatches": metrics.recent_mismatches,
        }
        self._state.write(self._state_path)


_MIGRATION_SERVICE: MigrationService | None = None


def get_migration_service() -> MigrationService:
    global _MIGRATION_SERVICE
    if _MIGRATION_SERVICE is None:
        _MIGRATION_SERVICE = MigrationService()
    return _MIGRATION_SERVICE


def set_migration_service(service: MigrationService | None) -> None:
    global _MIGRATION_SERVICE
    _MIGRATION_SERVICE = service


__all__ = [
    "MigrationPhase",
    "MigrationService",
    "get_migration_service",
    "set_migration_service",
    "MigrationState",
]

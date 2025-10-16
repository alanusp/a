from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Tuple

from app.core.clock_rng import get_clock, get_rng
from app.core.timing_guard import constant_time_compare, pad_failure, sleep_pad

try:  # pragma: no cover - optional dependency for runtime API surface
    from fastapi import HTTPException, status
except ImportError:  # pragma: no cover - fallback for test environments
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str) -> None:
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class status:  # type: ignore[no-redef]
        HTTP_401_UNAUTHORIZED = 401


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"


@dataclass
class ApiKeyRecord:
    key: str
    role: Role


class ApiKeyStore:
    def __init__(self, keys: Iterable[ApiKeyRecord] | None = None) -> None:
        self._keys: Dict[str, Role] = {}
        if keys:
            for record in keys:
                self._keys[record.key] = record.role

    def authorize(self, key: str, required_role: Role) -> bool:
        candidate_role: Role | None = None
        for stored_key, role in self._keys.items():
            if constant_time_compare(stored_key, key):
                candidate_role = role
        if candidate_role is None:
            return False
        if required_role == Role.VIEWER:
            return True
        return candidate_role == required_role

    def rotate(self, old_key: str, new_key: str) -> None:
        role = self._keys.pop(old_key, None)
        if role is None:
            raise KeyError("API key not found")
        self._keys[new_key] = role

    def insert(self, key: str, role: Role) -> None:
        self._keys[key] = role


class ApiKeyManager:
    def __init__(self, store: ApiKeyStore | None = None) -> None:
        self.store = store or ApiKeyStore()

    def authenticate(
        self, headers: Mapping[str, str], *, required_role: Role = Role.VIEWER
    ) -> Tuple[bool, float]:
        clock = get_clock()
        rng = get_rng()
        started = clock.now_ns()
        provided = headers.get("X-API-Key", "")
        allowed = self.store.authorize(provided, required_role)
        if allowed:
            return True, 0.0
        pad = pad_failure(clock=clock, rng=rng, started_ns=started)
        sleep_pad(pad)
        return False, pad.sleep_ms

    def rotate(self, old_key: str, new_key: str) -> None:
        self.store.rotate(old_key, new_key)


API_KEYS = ApiKeyManager()


def authorise_console(headers: Mapping[str, str]) -> None:
    allowed, pad_ms = API_KEYS.authenticate(headers, required_role=Role.VIEWER)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorised",
            headers={"X-Timing-Pad": f"{pad_ms:.3f}"},
        )

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Tuple

try:  # pragma: no cover - FastAPI may not be present during offline tooling
    from fastapi import HTTPException, status
except ModuleNotFoundError:  # pragma: no cover
    class status:  # type: ignore[no-redef]
        HTTP_503_SERVICE_UNAVAILABLE = 503

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: object) -> None:
            self.status_code = status_code
            self.detail = detail
            super().__init__(str(detail))


@dataclass(slots=True)
class FreezeStatus:
    enabled: bool
    retry_after: int
    note: str


def freeze_status() -> FreezeStatus:
    readonly, reason = _runtime_read_only()
    window = _maintenance_window_active()
    manual = os.getenv("MAINTENANCE_FREEZE", "0").lower() in {"1", "true", "yes"}
    enabled = readonly or window or manual
    retry_after = int(os.getenv("MAINTENANCE_RETRY_AFTER", "60"))
    note = os.getenv("MAINTENANCE_FREEZE_NOTE", "maintenance window in progress")
    if readonly and reason:
        note = f"{note}; reason={reason}"
    elif window:
        note = f"{note}; window"
    elif manual:
        note = f"{note}; manual"
    return FreezeStatus(enabled=enabled, retry_after=retry_after, note=note)


def enforce_writable(response_headers: dict[str, str] | None = None) -> None:
    readonly, reason = _runtime_read_only()
    if readonly:
        if response_headers is not None:
            response_headers["Retry-After"] = str(
                int(os.getenv("MAINTENANCE_RETRY_AFTER", "60"))
            )
            response_headers["X-Readonly-Reason"] = reason or "unspecified"
        detail = {"read_only": True, "reason": reason or "unspecified"}
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

    status_payload = freeze_status()
    if not status_payload.enabled:
        return
    if response_headers is not None:
        response_headers["Retry-After"] = str(status_payload.retry_after)
        if reason:
            response_headers.setdefault("X-Readonly-Reason", reason)
    detail = {
        "freeze": True,
        "retry_after": status_payload.retry_after,
        "note": status_payload.note,
    }
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


def _runtime_read_only() -> Tuple[bool, str | None]:
    try:
        from app.core.runtime_state import is_read_only

        return is_read_only()
    except Exception:  # pragma: no cover - defensive fall-back
        return False, None


def _maintenance_window_active() -> bool:
    windows_raw = os.getenv("MAINTENANCE_WINDOWS", "")
    if not windows_raw.strip():
        return False
    now = datetime.now(timezone.utc).time()
    for window in windows_raw.split(","):
        window = window.strip()
        if not window:
            continue
        try:
            start_raw, end_raw = window.split("-", 1)
            start = _parse_time(start_raw.strip())
            end = _parse_time(end_raw.strip())
        except ValueError:
            continue
        if start <= end:
            if start <= now <= end:
                return True
        else:  # overnight window
            if now >= start or now <= end:
                return True
    return False


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))

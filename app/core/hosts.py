from __future__ import annotations

try:  # pragma: no cover - FastAPI not available during offline tooling
    from fastapi import HTTPException
except ModuleNotFoundError:  # pragma: no cover - fallback for unit tests without FastAPI
    class HTTPException(RuntimeError):
        def __init__(self, status_code: int, detail: str) -> None:
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

from app.core.config import get_settings


def _allowed_hosts() -> list[str]:
    hosts = getattr(get_settings(), "allowed_hosts", ["localhost", "127.0.0.1"])
    return [host.lower() for host in hosts]


def enforce_allowed_host(headers: dict[str, str]) -> None:
    host = headers.get("host", "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="missing host header")
    if any(ch in host for ch in {"/", "\\", "\n", "\r"}):
        raise HTTPException(status_code=400, detail="invalid host header")
    hostname = host.split(":", 1)[0].lower()
    allowed = _allowed_hosts()
    if "*" not in allowed and hostname not in allowed:
        raise HTTPException(status_code=400, detail="host not allowed")

    # sanitise proxy headers to avoid smuggling attacks
    for header in ("x-forwarded-host", "x-forwarded-proto", "x-forwarded-for"):
        value = headers.get(header)
        if value is None:
            continue
        cleaned = value.split(",")[0].strip()
        if any(ch in cleaned for ch in {"/", "\\", "\n", "\r"}):
            raise HTTPException(status_code=400, detail="invalid proxy header")


__all__ = ["enforce_allowed_host"]

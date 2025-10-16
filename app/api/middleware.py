from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.drain import get_drain_manager
from app.core.hosts import enforce_allowed_host
from app.core.json_strict import JsonSafetyError, strict_loads
from app.core.leak_sentinel import get_leak_sentinel
from app.core.runtime_state import read_only_reason, snapshot as runtime_snapshot
from app.core.staleness import get_staleness_monitor
from app.core.waf import inspect as waf_inspect
from app.core.mtls import export_spki_pin


def _fingerprint() -> str:
    manifest = Path("artifacts/version_manifest.json")
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            return payload.get("build", {}).get("sha256", "dev")
        except json.JSONDecodeError:
            return "dev"
    return "dev"


_BUILD_FINGERPRINT = _fingerprint()
_BASELINE_HASH = get_settings().api_baseline_hash


def install_api_middleware(app: FastAPI) -> None:
    settings = get_settings()
    deprecations = settings.api_deprecations

    @app.middleware("http")
    async def attach_headers(request: Request, call_next: Callable):  # type: ignore[override]
        enforce_allowed_host(dict(request.headers))

        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.body()
            if body:
                try:
                    strict_loads(body)
                except JsonSafetyError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                if settings.enable_waf:
                    decision = waf_inspect(body)
                    if not decision.allowed:
                        raise HTTPException(status_code=400, detail={"reason": decision.reason or "blocked"})

                async def new_receive() -> dict[str, object]:
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = new_receive  # type: ignore[attr-defined]

        drain = get_drain_manager()
        status = drain.status()
        if drain.should_block():
            reason = status.reason or "drain"
            response = JSONResponse(
                status_code=503,
                content={"detail": "drain in progress", "reason": reason},
            )
            response.headers.setdefault("Retry-After", "5")
            response.headers.setdefault("X-Drain-Reason", reason)
            response.headers.setdefault("X-Runtime-State", json.dumps(runtime_snapshot()))
            return response
        if drain.should_soft_throttle():
            reason = status.reason or "drain"
            response = JSONResponse(
                status_code=429,
                content={"detail": "drain throttling", "reason": reason},
            )
            response.headers.setdefault("Retry-After", "5")
            response.headers.setdefault("X-Drain-Reason", reason)
            response.headers.setdefault("X-Runtime-State", json.dumps(runtime_snapshot()))
            return response

        response = await call_next(request)
        response.headers.setdefault("X-Build-Fingerprint", _BUILD_FINGERPRINT)
        response.headers.setdefault("X-SPKI-Pin", export_spki_pin())
        if _BASELINE_HASH and _BASELINE_HASH != "dev":
            response.headers.setdefault("X-API-Baseline-Hash", _BASELINE_HASH)
        active_route = getattr(request.state, "active_route", None)
        if active_route:
            response.headers.setdefault("X-Route-Decision", str(active_route))
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            response.headers.setdefault("X-Retry-After", retry_after)
        stale = get_staleness_monitor().stale()
        if stale:
            response.headers.setdefault("X-Stale-Model", "true")
        readonly = read_only_reason()
        if readonly:
            response.headers.setdefault("X-Readonly-Reason", readonly)
        response.headers.setdefault("X-Runtime-State", json.dumps(runtime_snapshot()))
        leak_sentinel = get_leak_sentinel()
        if not leak_sentinel.healthy():
            response.headers.setdefault("X-Leak-Alarm", "true")
        if status.reason:
            response.headers.setdefault("X-Drain-Reason", status.reason)
        path = request.url.path
        if path in deprecations:
            response.headers.setdefault("Deprecation", "true")
            response.headers.setdefault("Sunset", deprecations[path])
        return response

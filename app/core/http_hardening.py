from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        settings = get_settings()
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", settings.csp_policy)
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        settings = get_settings()
        length_header = request.headers.get("content-length")
        if length_header is not None:
            try:
                size = int(length_header)
            except ValueError:
                size = settings.max_request_body + 1
            if size > settings.max_request_body:
                raise HTTPException(status_code=413, detail="payload too large")
        body = await request.body()
        if len(body) > settings.max_request_body:
            raise HTTPException(status_code=413, detail="payload too large")
        async def new_receive() -> dict[str, object]:
            return {"type": "http.request", "body": body, "more_body": False}
        request._receive = new_receive  # type: ignore[attr-defined]
        return await call_next(request)


class SlowLorisMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        settings = get_settings()
        try:
            return await asyncio.wait_for(call_next(request), timeout=settings.read_timeout_seconds)
        except asyncio.TimeoutError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=408, detail="request timeout") from exc


def install_http_hardening(app) -> None:
    app.add_middleware(SlowLorisMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

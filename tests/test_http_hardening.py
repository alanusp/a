from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
Body = fastapi.Body
FastAPI = fastapi.FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from app.core.http_hardening import install_http_hardening


def create_app() -> FastAPI:
    app = FastAPI()
    install_http_hardening(app)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/echo")
    async def echo(payload: str = Body(...)) -> dict[str, int]:
        return {"length": len(payload)}

    return app


def test_security_headers_present(monkeypatch):
    monkeypatch.setenv("CONTENT_SECURITY_POLICY", "default-src 'self'")
    app = create_app()
    client = TestClient(app)
    response = client.get("/ping")
    assert response.headers["content-security-policy"] == "default-src 'self'"
    assert response.headers["strict-transport-security"].startswith("max-age")


def test_body_size_limit(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BODY", "16")
    app = create_app()
    client = TestClient(app)
    assert client.post("/echo", data="small").status_code == 200
    response = client.post("/echo", data="x" * 32)
    assert response.status_code == 413

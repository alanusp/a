"""Auto-generated client. Do not edit by hand."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

spec_version = "0.0.0"

__all__ = ["FraudApiClient", "ClientError"]


def _baseline_hash() -> str:
    manifest = Path("artifacts/version_manifest.json")
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            openapi = payload.get("openapi", {})
            if isinstance(openapi, dict):
                return str(openapi.get("sha256", "dev"))
        except json.JSONDecodeError:
            pass
    return "dev"


@dataclass
class ClientError(Exception):
    status_code: int
    detail: Any


class FraudApiClient:
    """Typed httpx client generated from the project OpenAPI specification."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        spki_pin: Optional[str] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._baseline = _baseline_hash()
        headers: Dict[str, str] = {"X-API-Baseline-Hash": self._baseline}
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(base_url=self._base_url, headers=headers, timeout=timeout)
        self._spki_pin = spki_pin
        self.version = spec_version
        self.last_quota_remaining: float | None = None

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        response = self._client.request(method, path, params=params, json=json_body)
        if self._spki_pin:
            header_pin = response.headers.get("X-SPKI-Pin")
            if header_pin != self._spki_pin:
                raise ClientError(status_code=598, detail={"error": "spki-mismatch"})
        if "X-RateLimit-Remaining" in response.headers:
            try:
                self.last_quota_remaining = float(response.headers["X-RateLimit-Remaining"])
            except ValueError:
                self.last_quota_remaining = None
        if response.status_code >= 400:
            raise ClientError(status_code=response.status_code, detail=response.json())
        return response

    # Example method placeholders for parity tests
    def predict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request("POST", "/v1/predict", json_body=payload)
        return response.json()

    def feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request("POST", "/v1/feedback", json_body=payload)
        return response.json()

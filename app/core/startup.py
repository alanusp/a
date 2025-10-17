from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from app.core.config import get_settings

_GOLDEN_REQUEST_PATH = Path("artifacts/golden/predict.json")


@dataclass(slots=True)
class StartupState:
    ready: bool = False
    startup_time_ms: float = 0.0
    error: str | None = None


class StartupManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.state = StartupState()
        self._warmed = False

    def warm(self, *, force: bool = False) -> StartupState:
        if self._warmed and not force:
            return self.state

        payload = self._load_sample_payload()
        start = time.perf_counter()
        inference_service, feature_service = self._resolve_services()
        features = feature_service.to_feature_list(payload)
        inference_service.predict(features)
        elapsed_ms = (time.perf_counter() - start) * 1_000
        self.state.startup_time_ms = elapsed_ms
        budget = getattr(self.settings, "cold_start_budget_ms", 5_000)
        if elapsed_ms <= budget:
            self.state.ready = True
            self.state.error = None
        else:
            self.state.ready = False
            self.state.error = (
                f"startup time {elapsed_ms:.1f}ms exceeded budget {budget}ms"
            )
        self._warmed = True
        return self.state

    def _resolve_services(self):
        from app.services.feature_service import FeatureService
        from app.services.inference_service import InferenceService

        return InferenceService(), FeatureService()

    def _load_sample_payload(self) -> Dict[str, Any]:
        if _GOLDEN_REQUEST_PATH.exists():
            try:
                data = json.loads(_GOLDEN_REQUEST_PATH.read_text(encoding="utf-8"))
                request = data.get("request")
                if isinstance(request, dict):
                    return request
            except json.JSONDecodeError:
                pass
        return {
            "transaction_id": "startup-txn",
            "customer_id": "startup-customer",
            "merchant_id": "startup-merchant",
            "device_id": "startup-device",
            "card_id": "startup-card",
            "ip_address": "127.0.0.1",
            "amount": 42.0,
            "currency": "USD",
            "device_trust_score": 0.5,
            "merchant_risk_score": 0.5,
            "velocity_1m": 0.0,
            "velocity_1h": 0.0,
            "chargeback_rate": 0.0,
            "account_age_days": 180.0,
            "customer_tenure": 365.0,
            "geo_distance": 10.0,
        }


_MANAGER: StartupManager | None = None


def get_startup_manager() -> StartupManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = StartupManager()
    return _MANAGER


def warm_startup(force: bool = False) -> StartupState:
    return get_startup_manager().warm(force=force)


def get_startup_state() -> StartupState:
    return get_startup_manager().state


def reset_startup_state() -> None:
    global _MANAGER
    _MANAGER = None

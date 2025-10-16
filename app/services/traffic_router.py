from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, Tuple

from app.core.config import get_settings
from app.core.runtime_state import is_safe_mode
from app.core.flags import FeatureFlagSet, get_feature_flags


@dataclass(slots=True)
class RouteSnapshot:
    baseline: float
    candidate: float
    sticky_hits: int
    overrides: int
    safe_mode: bool
    routes: Dict[str, float]


class TrafficRouter:
    """Deterministic percentage-based router with sticky hashing."""

    def __init__(
        self,
        *,
        flags: FeatureFlagSet | None = None,
        settings=None,
    ) -> None:
        self._flags = flags or get_feature_flags()
        self._settings = settings or get_settings()
        self._metrics: Dict[str, int] = {"override": 0, "sticky": 0}
        self._route_hits: Dict[str, int] = {}
        self._last_weights: Dict[str, float] = {"baseline": 1.0}

    def _parse_weights(self) -> Dict[str, float]:
        flag_value = self._flags.value("traffic.routes", None)
        weights: Dict[str, float] = {}
        if flag_value:
            if isinstance(flag_value, str):
                try:
                    parsed = json.loads(flag_value)
                except json.JSONDecodeError:
                    parsed = {}
            elif isinstance(flag_value, dict):
                parsed = flag_value
            else:
                parsed = {}
            for key, value in parsed.items():
                try:
                    weight = float(value)
                except (TypeError, ValueError):
                    continue
                if weight > 0:
                    weights[str(key)] = weight
        if not weights:
            raw_flag = self._flags.value("traffic.candidate_pct", None)
            candidate_pct: float
            if raw_flag is not None:
                try:
                    candidate_pct = float(raw_flag)
                except (TypeError, ValueError):
                    candidate_pct = 0.0
            else:
                candidate_pct = float(getattr(self._settings, "candidate_traffic_percent", 0.0))
            candidate_pct = max(0.0, min(100.0, candidate_pct))
            if candidate_pct > 0:
                weights = {"baseline": max(1.0 - candidate_pct / 100.0, 1e-6), "candidate": candidate_pct / 100.0}
            else:
                weights = {"baseline": 1.0}
        if "baseline" not in weights:
            weights["baseline"] = 1.0
        # normalise for reporting only (selection uses raw weights)
        total = sum(weights.values()) or 1.0
        return {name: weight / total for name, weight in weights.items()}

    @staticmethod
    def _hash_score(key: str, route: str) -> float:
        digest = hashlib.blake2b(f"{key}:{route}".encode("utf-8"), digest_size=16).digest()
        return int.from_bytes(digest, "big") / float(1 << 128)

    def _choose_route(self, key: str) -> Tuple[str, Dict[str, float]]:
        weights = self._parse_weights()
        best_route = "baseline"
        best_score = -1.0
        for route, weight in weights.items():
            if weight <= 0:
                continue
            score = self._hash_score(key, route) * weight
            if score > best_score:
                best_route = route
                best_score = score
        return best_route, weights

    def select(
        self,
        *,
        tenant_id: str,
        event_id: str,
        safe_mode: bool = False,
    ) -> str:
        safe_mode = safe_mode or is_safe_mode() or self._flags.enabled("traffic.safe_mode")
        if safe_mode:
            self._metrics["override"] = self._metrics.get("override", 0) + 1
            self._route_hits["baseline"] = self._route_hits.get("baseline", 0) + 1
            return "baseline"

        key = f"{tenant_id}:{event_id}"
        route, weights = self._choose_route(key)
        self._last_weights = weights
        self._route_hits[route] = self._route_hits.get(route, 0) + 1
        if route != "baseline":
            self._metrics["sticky"] = self._metrics.get("sticky", 0) + 1
        return route

    def override_to_baseline(self) -> None:
        self._metrics["override"] += 1

    def snapshot(self, *, safe_mode: bool) -> RouteSnapshot:
        total = max(1, sum(self._route_hits.values()))
        routes = {name: hits / total for name, hits in self._route_hits.items()}
        if not routes:
            routes = {name: weight for name, weight in self._last_weights.items()}
        baseline_pct = routes.get("baseline", 0.0)
        candidate_pct = sum(value for name, value in routes.items() if name != "baseline")
        return RouteSnapshot(
            baseline=baseline_pct,
            candidate=candidate_pct,
            sticky_hits=self._metrics.get("sticky", 0),
            overrides=self._metrics.get("override", 0),
            safe_mode=safe_mode,
            routes=routes,
        )


_ROUTER: TrafficRouter | None = None


def get_traffic_router() -> TrafficRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = TrafficRouter()
    return _ROUTER

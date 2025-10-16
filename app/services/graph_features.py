from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Dict, Mapping, Tuple

from app.core.cache import NegativeCache, TTLCache
from app.core.config import get_settings
from app.core.shutdown import get_shutdown_coordinator
from app.core.singleflight import SingleFlight
from graph.engine import get_graph_engine

_GRAPH_FEATURE_NAMES = [
    "customer_degree",
    "customer_component",
    "shared_device_customers",
    "merchant_degree",
    "customer_to_merchant_steps",
    "triangle_count",
    "neighbour_risk",
    "customer_ppr_focus",
    "customer_ego_betweenness",
]


class GraphFeatureService:
    def __init__(self) -> None:
        self.engine = get_graph_engine()
        settings = get_settings()
        ttl = float(getattr(settings, "graph_cache_ttl_seconds", 5.0))
        max_size = int(getattr(settings, "graph_cache_max_entries", 2048))
        negative_ttl = float(getattr(settings, "graph_negative_ttl_seconds", 2.0))
        self._cache = TTLCache(
            "graph_features",
            ttl_seconds=ttl,
            jitter=0.15,
            max_size=max_size,
        )
        self._negative = NegativeCache(
            "graph_missing",
            ttl_seconds=negative_ttl,
            jitter=0.1,
            max_size=max(256, max_size // 4),
        )
        self._flight = SingleFlight(ttl_seconds=float(getattr(settings, "singleflight_ttl_seconds", 5.0)))
        get_shutdown_coordinator().register("graph_snapshot", lambda timeout: self.engine.flush())

    def _key(self, relationships: Mapping[str, str]) -> Tuple[Tuple[str, str], ...]:
        return tuple(sorted(relationships.items()))

    def update(
        self,
        event_id: str,
        payload: Dict[str, str | float | None],
        *,
        fraud_probability: float,
    ) -> Dict[str, float]:
        relationships = {
            "customer_id": str(payload.get("customer_id", "")) or "",
            "device_id": str(payload.get("device_id", "")) or "",
            "merchant_id": str(payload.get("merchant_id", "")) or "",
            "card_id": str(payload.get("card_id", "")) or "",
            "ip_address": str(payload.get("ip_address", "")) or "",
        }
        relationships = {k: v for k, v in relationships.items() if v}
        self.engine.ingest(
            event_id=event_id,
            timestamp=datetime.utcnow(),
            relationships=relationships,
            fraud_probability=fraud_probability,
        )
        key = self._key(relationships)
        metrics = self.engine.compute_metrics(relationships)
        if key:
            self._cache.set(key, dict(metrics))
            self._negative.invalidate(key)
        return metrics

    def compute_features(self, payload: Dict[str, str | float | None]) -> Dict[str, float]:
        relationships = {
            "customer_id": str(payload.get("customer_id", "")) or "",
            "device_id": str(payload.get("device_id", "")) or "",
            "merchant_id": str(payload.get("merchant_id", "")) or "",
            "card_id": str(payload.get("card_id", "")) or "",
            "ip_address": str(payload.get("ip_address", "")) or "",
        }
        relationships = {k: v for k, v in relationships.items() if v}
        key = self._key(relationships)
        if key and self._negative.contains(key):
            return {name: 0.0 for name in _GRAPH_FEATURE_NAMES}
        if key:
            cached, payload_metrics = self._cache.get(key)
            if cached:
                return {
                    name: float(payload_metrics.get(name, 0.0))
                    for name in _GRAPH_FEATURE_NAMES
                }

        def _compute() -> Dict[str, float]:
            metrics = self.engine.compute_metrics(relationships)
            if key:
                if any(float(metrics.get(name, 0.0)) != 0.0 for name in _GRAPH_FEATURE_NAMES):
                    self._cache.set(key, dict(metrics))
                else:
                    self._negative.remember(key)
            return metrics

        metrics = self._flight.run(
            "graph:" + ",".join(f"{k}={v}" for k, v in key) if key else "graph:none",
            _compute,
        )
        return {name: float(metrics.get(name, 0.0)) for name in _GRAPH_FEATURE_NAMES}

    @property
    def feature_names(self) -> list[str]:
        return list(_GRAPH_FEATURE_NAMES)

    def flush(self, timeout: float) -> None:
        self.engine.flush()


@lru_cache
def get_graph_feature_service() -> GraphFeatureService:
    return GraphFeatureService()

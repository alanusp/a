from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, List

from app.core.config import get_settings
from app.core.singleflight import SingleFlight
from app.services.graph_features import get_graph_feature_service
from app.services.sketch_book import get_sketch_book

try:  # pragma: no cover - the optional dependency is exercised in integration tests
    from feast import FeatureStore
except ImportError:  # pragma: no cover - fallback for unit-test environments
    FeatureStore = None  # type: ignore[assignment]


@lru_cache
def _feature_names() -> List[str]:
    base = [
        "amount",
        "customer_tenure",
        "device_trust_score",
        "merchant_risk_score",
        "velocity_1m",
        "velocity_1h",
        "chargeback_rate",
        "account_age_days",
        "geo_distance",
    ]
    return base


class FeatureService:
    def __init__(self) -> None:
        settings = get_settings()
        self.repo_path = settings.feast_repo_path
        self.feature_view_name = "transaction_features"
        self.base_feature_names = _feature_names()
        self.graph_service = get_graph_feature_service()
        self.sketch_book = get_sketch_book()
        self.sketch_feature_names = [
            "replay_flag",
            "merchant_frequency_estimate",
            "device_frequency_estimate",
            "unique_customer_estimate",
        ]
        self.feature_names = (
            self.base_feature_names
            + self.graph_service.feature_names
            + self.sketch_feature_names
        )
        self._store: FeatureStore | None = None
        self._feast_flight = SingleFlight(ttl_seconds=float(getattr(settings, "singleflight_ttl_seconds", 5.0)))

    def _store_instance(self) -> FeatureStore:
        if FeatureStore is None:
            raise RuntimeError(
                "Feast is not installed. Install the 'feast' extra or run inside the provided "
                "Docker environment to access the online feature store."
            )
        if self._store is None:
            self._store = FeatureStore(repo_path=str(self.repo_path))
        return self._store

    def fetch_online_features(
        self, entity_rows: Iterable[Dict[str, int | str]]
    ) -> list[list[float]]:
        import numpy as np

        rows = list(entity_rows)
        key = self._entity_key(rows)

        def _fetch() -> list[list[float]]:
            store = self._store_instance()
            feature_vector = store.get_online_features(
                features=[f"{self.feature_view_name}:{name}" for name in self.base_feature_names],
                entity_rows=rows,
            )
            df = feature_vector.to_df()
            vector = df[[f"{self.feature_view_name}__{name}" for name in self.base_feature_names]].to_numpy(
                dtype=np.float32
            )
            return vector.tolist()

        return self._feast_flight.run(key, _fetch)

    def to_feature_list(self, payload: Dict[str, float | int | str]) -> List[float]:
        """Convert API payload into ordered feature list expected by the model."""

        numeric_features = [float(payload.get(name, 0.0)) for name in self.base_feature_names]
        graph_metrics = self.graph_service.compute_features(payload)
        ordered_graph = [graph_metrics.get(name, 0.0) for name in self.graph_service.feature_names]
        sketch_metrics = self.sketch_book.observe(
            str(payload.get("event_id", "")) or payload.get("transaction_id", ""),
            customer_id=str(payload.get("customer_id", "anon")),
            device_id=str(payload.get("device_id", "unknown")),
            merchant_id=str(payload.get("merchant_id", "unknown")),
        )
        ordered_sketch = [sketch_metrics.get(name, 0.0) for name in self.sketch_feature_names]
        return numeric_features + ordered_graph + ordered_sketch

    @staticmethod
    def _entity_key(entity_rows: Iterable[Dict[str, int | str]]) -> str:
        normalised: List[Tuple[str, str]] = []
        for row in entity_rows:
            normalised.extend((str(key), str(value)) for key, value in sorted(row.items()))
        return "|".join(f"{k}:{v}" for k, v in normalised)

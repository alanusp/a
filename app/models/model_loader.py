from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

from app.core.config import get_settings
from app.core.cache import NegativeCache
from app.core.singleflight import SingleFlight


@dataclass(slots=True)
class LogisticModel:
    weights: tuple[float, ...]
    bias: float

    def predict_proba(self, features: Iterable[float]) -> float:
        z = self.bias
        for weight, feature in zip(self.weights, features):
            z += weight * float(feature)
        return 1.0 / (1.0 + math.exp(-z))


_MODEL_FLIGHT: SingleFlight[Tuple["LogisticModel", str]] = SingleFlight(ttl_seconds=5.0)
_MISSING_MODELS = NegativeCache("model_missing", ttl_seconds=15.0, jitter=0.1, max_size=16)


def _load_weights(path: Path) -> Tuple[tuple[float, ...], float]:
    if not path.exists():
        raise FileNotFoundError(f"Model artifact not found at {path}")
    with open(path) as fp:
        payload = json.load(fp)
    weights = tuple(float(x) for x in payload["weights"])
    bias = float(payload["bias"])
    return weights, bias


def load_model(model_path: Path | None = None) -> Tuple[LogisticModel, str]:
    settings = get_settings()
    path = model_path or settings.model_path
    cache_key = str(path.resolve())
    if _MISSING_MODELS.contains(cache_key):
        raise FileNotFoundError(f"Model artifact not found at {path} (cached)")

    def _load() -> Tuple[LogisticModel, str]:
        weights, bias = _load_weights(path)
        if len(weights) != settings.model_input_dim:
            raise ValueError(
                f"Model weight dimension {len(weights)} does not match configured input dim "
                f"{settings.model_input_dim}."
            )
        return LogisticModel(weights=weights, bias=bias), "cpu"

    try:
        return _MODEL_FLIGHT.run(cache_key, _load)
    except FileNotFoundError:
        _MISSING_MODELS.remember(cache_key)
        raise


def infer(model: LogisticModel, device: str, features: Iterable[float]) -> float:  # noqa: ARG001
    return model.predict_proba(features)

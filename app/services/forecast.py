from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List


@dataclass(slots=True)
class EWMA:
    alpha: float = 0.2
    _value: float | None = None

    def update(self, observation: float) -> float:
        if self._value is None:
            self._value = observation
        else:
            self._value = self.alpha * observation + (1 - self.alpha) * self._value
        return self._value

    @property
    def value(self) -> float:
        return float(self._value or 0.0)


@dataclass(slots=True)
class HoltWinters:
    alpha: float = 0.4
    beta: float = 0.1
    gamma: float = 0.1
    season_length: int = 24
    _level: float = 0.0
    _trend: float = 0.0
    _seasonals: List[float] = field(default_factory=list)
    _initialized: bool = False

    def update(self, index: int, value: float) -> float:
        if not self._initialized:
            self._seasonals = [value] * self.season_length
            self._level = value
            self._trend = 0.0
            self._initialized = True
            return value
        seasonal = self._seasonals[index % self.season_length]
        last_level = self._level
        self._level = self.alpha * (value - seasonal) + (1 - self.alpha) * (self._level + self._trend)
        self._trend = self.beta * (self._level - last_level) + (1 - self.beta) * self._trend
        self._seasonals[index % self.season_length] = self.gamma * (value - self._level) + (1 - self.gamma) * seasonal
        return self._level + self._trend + self._seasonals[index % self.season_length]

    def forecast(self, index: int, horizon: int = 1) -> float:
        if not self._initialized:
            return 0.0
        seasonal = self._seasonals[(index + horizon) % self.season_length]
        return self._level + horizon * self._trend + seasonal


@dataclass(slots=True)
class ThresholdForecaster:
    alpha: float = 0.2
    holt_params: tuple[float, float, float] = (0.4, 0.1, 0.1)
    ewma: Dict[str, EWMA] = field(default_factory=dict)
    holt: Dict[str, HoltWinters] = field(default_factory=dict)

    def update(self, segment: str, timestamp_index: int, prevalence: float) -> Dict[str, float]:
        ewma = self.ewma.setdefault(segment, EWMA(alpha=self.alpha))
        smoothed = ewma.update(prevalence)
        hw = self.holt.setdefault(
            segment,
            HoltWinters(
                alpha=self.holt_params[0],
                beta=self.holt_params[1],
                gamma=self.holt_params[2],
            ),
        )
        trend = hw.update(timestamp_index, prevalence)
        seasonal = hw.forecast(timestamp_index, 1)
        recommended = min(max((smoothed + trend + seasonal) / 3.0, 0.01), 0.99)
        return {
            "segment": segment,
            "ewma": smoothed,
            "trend": trend,
            "seasonal": seasonal,
            "recommended_threshold": recommended,
        }

    def schedule(self, segment: str, horizon: int = 24) -> List[float]:
        hw = self.holt.get(segment)
        if not hw:
            return [0.0] * horizon
        current_index = len(hw._seasonals) - 1 if hw._seasonals else 0
        return [max(min(hw.forecast(current_index, step + 1), 1.0), 0.0) for step in range(horizon)]

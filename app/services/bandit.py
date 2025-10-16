from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, List, MutableMapping


@dataclass
class ArmState:
    threshold: float
    successes: float = 0.0
    failures: float = 0.0
    pulls: int = 0
    guardrail_breaches: int = 0
    reward_sum: float = 0.0

    @property
    def total(self) -> float:
        return self.successes + self.failures

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / max(self.pulls, 1)


@dataclass
class SegmentBandit:
    strategy: str
    arms: List[ArmState]
    total_pulls: int = 0
    exploration: float = 2.0

    def select_arm(self) -> ArmState:
        if self.strategy == "ucb":
            return self._select_ucb()
        if self.strategy == "thompson":
            return self._select_thompson()
        raise ValueError(f"Unknown strategy: {self.strategy}")

    def _select_ucb(self) -> ArmState:
        self.total_pulls = max(self.total_pulls, 1)
        scores: List[tuple[float, ArmState]] = []
        for arm in self.arms:
            if arm.guardrail_breaches > 0:
                continue
            if arm.pulls == 0:
                return arm
            bonus = math.sqrt(self.exploration * math.log(self.total_pulls) / arm.pulls)
            scores.append((arm.mean_reward + bonus, arm))
        if not scores:
            return min(self.arms, key=lambda arm: arm.guardrail_breaches)
        scores.sort(key=lambda item: item[0], reverse=True)
        return scores[0][1]

    def _select_thompson(self) -> ArmState:
        samples: List[tuple[float, ArmState]] = []
        for arm in self.arms:
            if arm.guardrail_breaches > 0:
                continue
            alpha = 1.0 + arm.successes
            beta = 1.0 + arm.failures
            samples.append((random.betavariate(alpha, beta), arm))
        if not samples:
            return min(self.arms, key=lambda arm: arm.guardrail_breaches)
        samples.sort(key=lambda item: item[0], reverse=True)
        return samples[0][1]

    def update(self, selected: ArmState, reward: float, guardrail_ok: bool) -> None:
        self.total_pulls += 1
        selected.pulls += 1
        selected.reward_sum += reward
        if reward >= 0:
            selected.successes += reward
        else:
            selected.failures += -reward
        if not guardrail_ok:
            selected.guardrail_breaches += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "total_pulls": self.total_pulls,
            "arms": [
                {
                    "threshold": arm.threshold,
                    "successes": arm.successes,
                    "failures": arm.failures,
                    "pulls": arm.pulls,
                    "guardrail_breaches": arm.guardrail_breaches,
                    "reward_sum": arm.reward_sum,
                }
                for arm in self.arms
            ],
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, object]) -> SegmentBandit:
        arms = [
            ArmState(
                threshold=float(item["threshold"]),
                successes=float(item.get("successes", 0.0)),
                failures=float(item.get("failures", 0.0)),
                pulls=int(item.get("pulls", 0)),
                guardrail_breaches=int(item.get("guardrail_breaches", 0)),
                reward_sum=float(item.get("reward_sum", 0.0)),
            )
            for item in payload.get("arms", [])
        ]
        return cls(
            strategy=str(payload.get("strategy", "ucb")),
            arms=arms,
            total_pulls=int(payload.get("total_pulls", 0)),
        )


class ThresholdBandit:
    """Threshold optimisation via contextual multi-armed bandits."""

    def __init__(
        self,
        thresholds: Iterable[float],
        *,
        strategy: str = "ucb",
        guardrail_tolerance: int = 3,
    ) -> None:
        unique_thresholds = sorted({round(value, 4) for value in thresholds})
        arms = [ArmState(threshold=value) for value in unique_thresholds]
        self._segments: MutableMapping[str, SegmentBandit] = {}
        self._defaults = (strategy, guardrail_tolerance)
        self.guardrail_tolerance = guardrail_tolerance
        self.prototype = SegmentBandit(strategy=strategy, arms=arms)

    def recommend(self, segment: str) -> float:
        bandit = self._segments.get(segment)
        if bandit is None:
            bandit = self._clone_prototype()
            self._segments[segment] = bandit
        arm = bandit.select_arm()
        return arm.threshold

    def observe(
        self,
        segment: str,
        threshold: float,
        *,
        reward: float,
        guardrail_ok: bool,
    ) -> None:
        bandit = self._segments.get(segment)
        if bandit is None:
            bandit = self._clone_prototype()
            self._segments[segment] = bandit
        for arm in bandit.arms:
            if math.isclose(arm.threshold, threshold, rel_tol=1e-9, abs_tol=1e-9):
                bandit.update(arm, reward, guardrail_ok)
                if arm.guardrail_breaches > self.guardrail_tolerance:
                    arm.guardrail_breaches = self.guardrail_tolerance
                break
        else:
            raise ValueError(f"Unknown threshold: {threshold}")

    def _clone_prototype(self) -> SegmentBandit:
        strategy, _ = self._defaults
        arms = [ArmState(**arm.__dict__) for arm in self.prototype.arms]
        return SegmentBandit(strategy=strategy, arms=arms)

    def snapshot(self) -> dict[str, object]:
        return {
            "guardrail_tolerance": self.guardrail_tolerance,
            "prototype": self.prototype.snapshot(),
            "segments": {key: bandit.snapshot() for key, bandit in self._segments.items()},
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, object]) -> ThresholdBandit:
        prototype_payload = payload.get("prototype")
        if not isinstance(prototype_payload, dict):
            raise TypeError("Missing prototype bandit in snapshot")
        prototype = SegmentBandit.from_snapshot(prototype_payload)
        instance = cls(
            [arm.threshold for arm in prototype.arms],
            strategy=prototype.strategy,
            guardrail_tolerance=int(payload.get("guardrail_tolerance", 3)),
        )
        instance.prototype = prototype
        segments_payload = payload.get("segments", {})
        if isinstance(segments_payload, dict):
            instance._segments = {
                key: SegmentBandit.from_snapshot(value)
                for key, value in segments_payload.items()
                if isinstance(value, dict)
            }
        return instance

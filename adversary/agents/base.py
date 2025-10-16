from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass
class AttackOutcome:
    success_rate: float
    tail_loss: float
    recovery_time: int


class AdversaryAgent:
    def __init__(self, name: str, *, seed: int = 42) -> None:
        self.name = name
        self.random = random.Random(seed)

    def simulate(self, deflection_rate: float, *, horizon: int = 100) -> AttackOutcome:
        raise NotImplementedError

    def _bounded_loss(self, samples: Iterable[float]) -> float:
        losses = sorted(samples)
        index = max(0, int(len(losses) * 0.9) - 1)
        return losses[index] if losses else 0.0


class CardTestingAgent(AdversaryAgent):
    def __init__(self, *, seed: int = 42) -> None:
        super().__init__("card_testing", seed=seed)

    def simulate(self, deflection_rate: float, *, horizon: int = 100) -> AttackOutcome:
        attempts = [self.random.random() for _ in range(horizon)]
        hits = sum(1 for sample in attempts if sample > deflection_rate)
        tail = self._bounded_loss([sample * 10 for sample in attempts])
        recovery = max(1, int(horizon * (1 - deflection_rate)))
        return AttackOutcome(success_rate=hits / horizon, tail_loss=tail, recovery_time=recovery)


class DeviceFarmAgent(AdversaryAgent):
    def __init__(self, *, seed: int = 99) -> None:
        super().__init__("device_farm", seed=seed)

    def simulate(self, deflection_rate: float, *, horizon: int = 100) -> AttackOutcome:
        attempts = [self.random.betavariate(2, 5) for _ in range(horizon)]
        hits = sum(1 for sample in attempts if sample > deflection_rate)
        tail = self._bounded_loss([sample * 20 for sample in attempts])
        recovery = max(1, int(horizon * (1 - deflection_rate) * 0.5))
        return AttackOutcome(success_rate=hits / horizon, tail_loss=tail, recovery_time=recovery)


def load_agents() -> List[AdversaryAgent]:
    return [CardTestingAgent(), DeviceFarmAgent()]


def evaluate_agents(deflection_rate: float, *, horizon: int = 100) -> Dict[str, AttackOutcome]:
    results: Dict[str, AttackOutcome] = {}
    for agent in load_agents():
        results[agent.name] = agent.simulate(deflection_rate, horizon=horizon)
    return results

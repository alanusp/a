from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable


class PrivacyBudgetExceeded(RuntimeError):
    """Raised when attempting to consume more privacy budget than allocated."""


@dataclass(slots=True)
class DifferentialPrivacyAccountant:
    """Track a simple epsilon privacy budget for metrics emission."""

    total_epsilon: float
    spent_epsilon: float = 0.0

    def remaining(self) -> float:
        return max(self.total_epsilon - self.spent_epsilon, 0.0)

    def charge(self, epsilon: float) -> None:
        if epsilon < 0:
            raise ValueError("epsilon must be positive")
        if self.spent_epsilon + epsilon > self.total_epsilon + 1e-9:
            raise PrivacyBudgetExceeded(
                f"Budget exceeded: requested {epsilon:.4f}, remaining {self.remaining():.4f}"
            )
        self.spent_epsilon += epsilon


def _laplace(scale: float, rnd: Callable[[], float]) -> float:
    u = rnd() - 0.5
    return -scale * math.copysign(math.log(1 - 2 * abs(u)), u)


def laplace_mechanism(
    value: float,
    *,
    epsilon: float,
    sensitivity: float = 1.0,
    accountant: DifferentialPrivacyAccountant | None = None,
    seed: int | None = None,
) -> float:
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    scale = sensitivity / epsilon
    rng = random.Random(seed)
    if accountant is not None:
        accountant.charge(epsilon)
    return value + _laplace(scale, rng.random)


def geometric_mechanism(
    value: int,
    *,
    epsilon: float,
    sensitivity: int = 1,
    accountant: DifferentialPrivacyAccountant | None = None,
    seed: int | None = None,
) -> int:
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if sensitivity <= 0:
        raise ValueError("sensitivity must be positive")
    rng = random.Random(seed)
    if accountant is not None:
        accountant.charge(epsilon)
    p = 1 - math.exp(-epsilon / sensitivity)
    geom = math.floor(math.log(1 - rng.random()) / math.log(1 - p))
    return value + int(geom)


def noisy_aggregate(
    values: Iterable[float],
    *,
    epsilon: float,
    accountant: DifferentialPrivacyAccountant,
    mechanism: Callable[..., float] = laplace_mechanism,
    seed: int | None = None,
) -> float:
    baseline = sum(values)
    return mechanism(
        baseline,
        epsilon=epsilon,
        accountant=accountant,
        seed=seed,
    )

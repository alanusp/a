from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Set, TYPE_CHECKING

from app.core.config import get_settings
from app.services.policy import PolicyDecision, PolicyService, evaluate_profit

if TYPE_CHECKING:
    from app.services.inference_service import InferenceService


@dataclass(slots=True)
class DecisionOutcome:
    action: str
    probability: float
    prediction_set: Set[int]
    threshold: float
    reasons: List[str]
    expected_cost: float
    policy: PolicyDecision


class DecisionService:
    """Blend model probabilities, conformal uncertainty, and policy rules."""

    def __init__(
        self,
        inference_service: "InferenceService",
        policy_service: PolicyService | None = None,
    ) -> None:
        self.settings = get_settings()
        self.inference_service = inference_service
        self.policy_service = policy_service or PolicyService()

    def decide(
        self,
        *,
        probability: float,
        features: Iterable[float],
        context: dict[str, Any],
        prediction_set: Set[int],
        strategy: str = "consensus",
    ) -> DecisionOutcome:
        _ = features
        threshold = self._optimal_threshold()
        model_action = "block" if probability >= threshold else "approve"
        policy = self.policy_service.decide(
            probability=probability,
            context=context,
            threshold_action=model_action,
            strategy=strategy,
        )
        action = policy.action
        expected_cost = self._expected_cost(probability, action)
        reasons = policy.reasons
        return DecisionOutcome(
            action=action,
            probability=probability,
            prediction_set=prediction_set,
            threshold=threshold,
            reasons=reasons,
            expected_cost=expected_cost,
            policy=policy,
        )

    def _optimal_threshold(self) -> float:
        model = self.inference_service.online_model
        return model.optimal_threshold(
            cost_false_positive=self.settings.cost_false_positive,
            cost_false_negative=self.settings.cost_false_negative,
            cost_true_positive=self.settings.cost_true_positive,
            cost_true_negative=self.settings.cost_true_negative,
        )

    def _expected_cost(self, probability: float, action: str) -> float:
        fp = self.settings.cost_false_positive
        fn = self.settings.cost_false_negative
        tp = self.settings.cost_true_positive
        tn = self.settings.cost_true_negative
        if action == "block":
            return probability * tp + (1.0 - probability) * fp
        return probability * fn + (1.0 - probability) * tn

    def profit_curve(self, probabilities: Iterable[float]) -> float:
        threshold = self._optimal_threshold()
        return evaluate_profit(
            probabilities,
            threshold=threshold,
            cost_false_positive=self.settings.cost_false_positive,
            cost_false_negative=self.settings.cost_false_negative,
            cost_true_positive=self.settings.cost_true_positive,
            cost_true_negative=self.settings.cost_true_negative,
        )

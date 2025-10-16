from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List

try:  # pragma: no cover - optional dependency for richer rule authoring
    import yaml
except ImportError:  # pragma: no cover - lightweight fallback parser
    yaml = None

from app.core.config import get_settings


_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
)


@dataclass(slots=True)
class Rule:
    name: str
    description: str
    action: str
    condition: str
    weight: float


@dataclass(slots=True)
class PolicyDecision:
    action: str
    matched_rules: List[str]
    reasons: List[str]
    strategy: str


class PolicyService:
    """Evaluate human-authored risk rules in a sandboxed interpreter."""

    def __init__(self, rules_path: Path | None = None) -> None:
        settings = get_settings()
        self.rules_path = rules_path or settings.policy_rules_path
        self.rules: List[Rule] = self._load_rules()

    def _load_rules(self) -> List[Rule]:
        rules: List[Rule] = []
        if not self.rules_path.exists():
            return rules
        for path in sorted(self.rules_path.glob("*.yaml")):
            payload = self._load_yaml(path.read_text())
            for entry in payload.get("rules", []):
                rule = Rule(
                    name=str(entry.get("name", path.stem)),
                    description=str(entry.get("description", "")),
                    action=str(entry.get("action", "review")),
                    condition=str(entry.get("condition", "False")),
                    weight=float(entry.get("weight", 1.0)),
                )
                self._validate_expression(rule.condition)
                rules.append(rule)
        return rules

    def decide(
        self,
        *,
        probability: float,
        context: dict[str, Any],
        threshold_action: str,
        strategy: str = "consensus",
    ) -> PolicyDecision:
        matches = [rule for rule in self.rules if self._evaluate(rule.condition, context)]
        if not matches:
            return PolicyDecision(
                action=threshold_action,
                matched_rules=[],
                reasons=["model_threshold"],
                strategy=strategy,
            )

        sorted_matches = sorted(matches, key=lambda rule: rule.weight, reverse=True)
        actions = {rule.action for rule in sorted_matches}
        if strategy == "rules-first":
            primary = sorted_matches[0]
            return PolicyDecision(
                action=primary.action,
                matched_rules=[rule.name for rule in sorted_matches],
                reasons=[primary.description or primary.name],
                strategy=strategy,
            )
        if strategy == "model-first":
            return PolicyDecision(
                action=threshold_action,
                matched_rules=[rule.name for rule in sorted_matches],
                reasons=[rule.description or rule.name for rule in sorted_matches]
                + ["model_threshold"],
                strategy=strategy,
            )
        if len(actions) == 1:
            action = actions.pop()
            return PolicyDecision(
                action=action,
                matched_rules=[rule.name for rule in sorted_matches],
                reasons=[rule.description or rule.name for rule in sorted_matches],
                strategy=strategy,
            )
        primary = sorted_matches[0]
        return PolicyDecision(
            action=primary.action,
            matched_rules=[rule.name for rule in sorted_matches],
            reasons=[
                primary.description or primary.name,
                "conflict_resolved_by_weight",
            ],
            strategy=strategy,
        )

    def _evaluate(self, expression: str, context: dict[str, Any]) -> bool:
        class _Default(dict):
            def __missing__(self, key: str) -> float:
                return 0.0

        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_NODES):
                raise ValueError(f"Unsupported expression node: {node.__class__.__name__}")
        compiled = compile(tree, filename="<policy>", mode="eval")
        safe_locals = _Default({key: context.get(key, 0.0) for key in context})
        return bool(eval(compiled, {"__builtins__": {}}, safe_locals))

    def _validate_expression(self, expression: str) -> None:
        self._evaluate(expression, {})

    def _load_yaml(self, text: str) -> dict[str, Any]:
        if yaml is not None:
            return yaml.safe_load(text)
        # Extremely small YAML subset: handle mappings with simple nesting.
        result: dict[str, Any] = {"rules": []}
        current: dict[str, Any] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("rules:"):
                continue
            if line.startswith("-"):
                if current:
                    result["rules"].append(current)
                current = {}
                continue
            if ":" in line and current is not None:
                key, value = line.split(":", 1)
                current[key.strip()] = value.strip()
        if current:
            result["rules"].append(current)
        return result


def evaluate_profit(
    probabilities: Iterable[float],
    *,
    threshold: float,
    cost_false_positive: float,
    cost_false_negative: float,
    cost_true_positive: float,
    cost_true_negative: float,
) -> float:
    expected = 0.0
    for probability in probabilities:
        if probability >= threshold:
            expected += probability * cost_true_positive + (1 - probability) * cost_false_positive
        else:
            expected += probability * cost_false_negative + (1 - probability) * cost_true_negative
    return expected

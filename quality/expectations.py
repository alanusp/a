from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Mapping


@dataclass
class ExpectationResult:
    passed: bool
    failures: list[str]


class ExpectationSuite:
    def __init__(self, expectations: Mapping[str, Dict[str, Any]]) -> None:
        self.expectations = expectations

    def validate(self, payload: Mapping[str, Any]) -> ExpectationResult:
        failures: list[str] = []
        for field, rules in self.expectations.items():
            value = payload.get(field)
            if value is None:
                if rules.get("required", False):
                    failures.append(f"{field} is required")
                continue
            if "min" in rules and value < rules["min"]:
                failures.append(f"{field} below minimum")
            if "max" in rules and value > rules["max"]:
                failures.append(f"{field} above maximum")
            if "allowed" in rules and value not in rules["allowed"]:
                failures.append(f"{field} outside allowed set")
            if "regex" in rules and not re.fullmatch(rules["regex"], str(value)):
                failures.append(f"{field} regex mismatch")
            if rules.get("freshness_seconds"):
                cutoff = datetime.utcnow() - timedelta(seconds=int(rules["freshness_seconds"]))
                timestamp = datetime.fromisoformat(str(value))
                if timestamp < cutoff:
                    failures.append(f"{field} is stale")
        return ExpectationResult(passed=not failures, failures=failures)


DEFAULT_EXPECTATIONS = ExpectationSuite(
    {
        "amount": {"min": 0.0},
        "currency": {"allowed": {"USD", "EUR", "GBP", "JPY"}},
        "transaction_id": {"regex": r"txn-[0-9]+", "required": True},
    }
)

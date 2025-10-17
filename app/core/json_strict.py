from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any


class JsonSafetyError(ValueError):
    pass


def _parse_constant(value: str) -> float:
    raise JsonSafetyError(f"non-finite numeric value '{value}' not allowed")


def strict_loads(data: bytes | str, *, max_depth: int = 64) -> Any:
    """Parse JSON rejecting NaN/Infinity and deep nesting."""

    obj = json.loads(data, parse_constant=_parse_constant)
    if _depth(obj) > max_depth:
        raise JsonSafetyError("json nesting depth exceeded")
    return obj


def _depth(value: Any, current: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return current + 1
        return max(_depth(v, current + 1) for v in value.values())
    if isinstance(value, list):
        if not value:
            return current + 1
        return max(_depth(v, current + 1) for v in value)
    return current + 1


def parse_money(value: str) -> Decimal:
    try:
        cents = Decimal(value)
    except (InvalidOperation, TypeError) as exc:  # pragma: no cover - defensive
        raise JsonSafetyError(f"invalid currency amount '{value}'") from exc
    quantized = cents.quantize(Decimal("0.01"))
    if quantized != cents:
        raise JsonSafetyError("currency value loses precision")
    return quantized

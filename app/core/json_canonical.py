"""Utilities for deterministic JSON Canonicalization Scheme (JCS).

The implementation follows RFC 8785 for the subset of JSON we use in the
application: objects with string keys, numbers, booleans, and lists.  We do not
attempt to canonicalise NaN/Infinity as they are not emitted by the platform.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

import json


def _normalise(value: Any) -> Any:
    """Recursively normalise Python values into canonical JSON primitives."""

    if isinstance(value, Mapping):
        return {str(key): _normalise(value[key]) for key in sorted(value.keys(), key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        # Use the shortest representation that round-trips via JSON
        return format(value.normalize(), "f").rstrip("0").rstrip(".") or "0"
    if isinstance(value, float):
        if value.is_integer():
            return format(int(value), "d")
        return format(value, ".15g")
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return str(value)


def canonicalize(payload: Any) -> str:
    """Return a canonical JSON string for *payload*.

    The output is stable across Python versions and platforms so that signed
    digests remain valid after transport.
    """

    normalised = _normalise(payload)
    return json.dumps(normalised, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

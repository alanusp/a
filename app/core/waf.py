"""Lightweight request anomaly scoring."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class WAFDecision:
    allowed: bool
    score: float
    reason: str | None = None


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = {}
    for byte in data:
        counts[byte] = counts.get(byte, 0) + 1
    total = float(len(data))
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def inspect(body: bytes, *, max_entropy: float = 7.5, max_length: int = 256_000) -> WAFDecision:
    if len(body) > max_length:
        return WAFDecision(allowed=False, score=1.0, reason="body-too-large")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return WAFDecision(allowed=False, score=1.0, reason="invalid-utf8")
    entropy = _entropy(body)
    if entropy > max_entropy:
        return WAFDecision(allowed=False, score=entropy, reason="high-entropy")
    if ".." in text or "\x00" in text:
        return WAFDecision(allowed=False, score=1.0, reason="path-traversal")
    return WAFDecision(allowed=True, score=entropy)

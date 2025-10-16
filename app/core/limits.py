from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from app.core.config import get_settings

LOGGER = logging.getLogger(__name__)

_SEVERITY_ORDER = {"ok": 0, "soft": 1, "hard": 2}


@dataclass(slots=True)
class LimitDecision:
    name: str
    current: int
    soft_limit: int
    hard_limit: int
    severity: str
    allowed: bool
    reason: Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "name": self.name,
            "current": self.current,
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "severity": self.severity,
            "allowed": self.allowed,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload

    @property
    def score(self) -> float:
        return float(_SEVERITY_ORDER.get(self.severity, 0))


class ResourceCap:
    def __init__(self, name: str, *, soft_limit: int, hard_limit: int) -> None:
        self.name = name
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self._last = LimitDecision(
            name=name,
            current=0,
            soft_limit=soft_limit,
            hard_limit=hard_limit,
            severity="ok",
            allowed=True,
        )

    def assess(self, value: int) -> LimitDecision:
        severity = "ok"
        reason: Optional[str] = None
        if self.hard_limit and value > self.hard_limit:
            severity = "hard"
            reason = f"{self.name}_hard_cap_exceeded"
        elif self.soft_limit and value > self.soft_limit:
            severity = "soft"
            reason = f"{self.name}_soft_cap_exceeded"
        return LimitDecision(
            name=self.name,
            current=value,
            soft_limit=self.soft_limit,
            hard_limit=self.hard_limit,
            severity=severity,
            allowed=severity != "hard",
            reason=reason,
        )

    def commit(self, value: int) -> LimitDecision:
        decision = self.assess(value)
        self._last = decision
        if decision.reason and decision.severity != "ok":
            LOGGER.warning(
                "resource limit breach",
                extra={
                    "resource": self.name,
                    "severity": decision.severity,
                    "current": decision.current,
                    "soft_limit": decision.soft_limit,
                    "hard_limit": decision.hard_limit,
                    "reason": decision.reason,
                },
            )
        return decision

    @property
    def last(self) -> LimitDecision:
        return self._last


class LimitRegistry:
    def __init__(self) -> None:
        settings = get_settings()
        self._resources: Dict[str, ResourceCap] = {
            "redis_stream": ResourceCap(
                "redis_stream",
                soft_limit=getattr(settings, "redis_stream_soft_cap", 1000),
                hard_limit=getattr(settings, "redis_stream_hard_cap", 1500),
            ),
            "graph_nodes": ResourceCap(
                "graph_nodes",
                soft_limit=getattr(settings, "graph_node_soft_cap", 50_000),
                hard_limit=getattr(settings, "graph_node_hard_cap", 75_000),
            ),
            "graph_edges": ResourceCap(
                "graph_edges",
                soft_limit=getattr(settings, "graph_edge_soft_cap", 100_000),
                hard_limit=getattr(settings, "graph_edge_hard_cap", 150_000),
            ),
            "sketch_cardinality": ResourceCap(
                "sketch_cardinality",
                soft_limit=getattr(settings, "sketch_cardinality_soft_cap", 200_000),
                hard_limit=getattr(settings, "sketch_cardinality_hard_cap", 250_000),
            ),
        }

    def for_resource(self, name: str) -> ResourceCap:
        if name not in self._resources:
            raise KeyError(f"unknown resource cap '{name}'")
        return self._resources[name]

    def report(self) -> Dict[str, Dict[str, object]]:
        return {name: cap.last.as_dict() for name, cap in self._resources.items()}

    def status_snapshot(self) -> Dict[str, Dict[str, object]]:
        return self.report()

    def export(self, path: Path) -> None:
        payload = self.report()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


_REGISTRY: LimitRegistry | None = None


def get_limit_registry() -> LimitRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = LimitRegistry()
    return _REGISTRY


def reset_limit_registry() -> None:
    global _REGISTRY
    _REGISTRY = None


def severity_score(severity: str) -> float:
    return float(_SEVERITY_ORDER.get(severity, 0))

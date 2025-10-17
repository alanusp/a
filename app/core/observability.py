from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping


_PII_PATTERN = re.compile(r"\b(\d{4,})\b")


def scrub_pii(value: str) -> str:
    return _PII_PATTERN.sub(lambda match: match.group(0)[:2] + "***" + match.group(0)[-2:], value)


def latency_exemplar(latency_ms: float, trace_id: str | None = None) -> Dict[str, Any]:
    exemplar = {"latency_ms": latency_ms}
    if trace_id:
        exemplar["trace_id"] = trace_id
    return exemplar


def json_log(message: str, *, context: Mapping[str, Any] | None = None) -> str:
    payload: Dict[str, Any] = {
        "timestamp": time.time(),
        "message": scrub_pii(message),
    }
    if context:
        payload.update({key: scrub_pii(str(value)) if isinstance(value, str) else value for key, value in context.items()})
    return json.dumps(payload, sort_keys=True)


@dataclass
class AuditEvent:
    action: str
    actor: str
    metadata: Dict[str, Any]
    timestamp: float

    def to_json(self) -> str:
        return json.dumps(
            {
                "action": self.action,
                "actor": scrub_pii(self.actor),
                "metadata": {key: scrub_pii(str(value)) for key, value in self.metadata.items()},
                "timestamp": self.timestamp,
            },
            sort_keys=True,
        )


class AuditLogger:
    def __init__(self, sink: Callable[[str], None]) -> None:
        self._sink = sink

    def log(self, action: str, actor: str, metadata: Dict[str, Any] | None = None) -> AuditEvent:
        event = AuditEvent(
            action=action,
            actor=actor,
            metadata=metadata or {},
            timestamp=time.time(),
        )
        self._sink(event.to_json())
        return event

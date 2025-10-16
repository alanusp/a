from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from typing import Dict, Tuple

LAMPORT_KEY = "lamport"
TRACE_HEADER = "traceparent"


@dataclass(slots=True, frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    lamport: int


class LamportClock:
    def __init__(self) -> None:
        seed = int(os.getenv("LAMPORT_SEED", "0"))
        self._value = seed
        self._lock = threading.Lock()

    def tick(self, external: int | None = None) -> int:
        with self._lock:
            if external is not None:
                self._value = max(self._value, external)
            self._value += 1
            return self._value


_CLOCK = LamportClock()


def _generate_span_id() -> str:
    return secrets.token_hex(8)


def _generate_trace_id() -> str:
    return secrets.token_hex(16)


def _parse_traceparent(header: str) -> Tuple[str, str, str, str]:
    parts = header.split("-")
    if len(parts) != 4:
        raise ValueError("invalid traceparent header")
    return tuple(parts)  # type: ignore[return-value]


def start_trace(headers: Dict[str, str]) -> TraceContext:
    parent = headers.get("traceparent") or headers.get("Traceparent")
    external_lamport = None
    if parent:
        try:
            _, trace_id, parent_span_id, _ = _parse_traceparent(parent)
        except ValueError:
            trace_id = _generate_trace_id()
            parent_span_id = None
        else:
            lamport_value = headers.get("x-lamport") or headers.get("X-Lamport")
            if lamport_value is not None:
                try:
                    external_lamport = int(lamport_value)
                except ValueError:
                    external_lamport = None
    else:
        trace_id = _generate_trace_id()
        parent_span_id = None
    span_id = _generate_span_id()
    lamport = _CLOCK.tick(external_lamport)
    return TraceContext(trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id, lamport=lamport)


def propagate_headers(context: TraceContext) -> Dict[str, str]:
    traceparent_value = f"00-{context.trace_id}-{context.span_id}-01"
    return {
        TRACE_HEADER: traceparent_value,
        "x-trace-id": context.trace_id,
        "x-span-id": context.span_id,
        "x-lamport": str(context.lamport),
    }


def event_identifier(context: TraceContext, *, tenant_id: str, transaction_id: str) -> str:
    return f"{tenant_id}-{context.trace_id}-{context.lamport:016x}-{transaction_id}".lower()

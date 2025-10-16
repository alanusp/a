from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

SCHEMA_REGISTRY: dict[str, str] = {
    "online_model": "2024-07-01",
    "graph_state": "2024-07-01",
    "idempotency": "2024-07-01",
}


class SnapshotSchemaError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotEnvelope:
    schema_version: str
    created_at: str
    payload: dict[str, object]


def schema_version_for(channel: str) -> str:
    return SCHEMA_REGISTRY.get(channel, "2024-07-01")


def stamp_snapshot(channel: str, payload: dict[str, object]) -> SnapshotEnvelope:
    return SnapshotEnvelope(
        schema_version=schema_version_for(channel),
        created_at=datetime.now(timezone.utc).isoformat(),
        payload=payload,
    )


def extract_snapshot(channel: str, envelope: dict[str, object]) -> SnapshotEnvelope:
    version = envelope.get("schema_version")
    expected = schema_version_for(channel)
    if version != expected:
        raise SnapshotSchemaError(f"snapshot schema mismatch for {channel}: {version} != {expected}")
    created_at = envelope.get("created_at")
    if not isinstance(created_at, str):
        raise SnapshotSchemaError("snapshot missing creation timestamp")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise SnapshotSchemaError("snapshot payload must be object")
    return SnapshotEnvelope(schema_version=expected, created_at=created_at, payload=payload)

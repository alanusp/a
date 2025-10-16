from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from app.core.config import get_settings
from app.core.trace import TraceContext


class LineageEmitter:
    """Emit OpenLineage-like events to a local JSONL sink."""

    def __init__(self, directory: Path | None = None) -> None:
        settings = get_settings()
        self.directory = directory or settings.lineage_directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.schema_version = "1.0"

    def emit(
        self,
        *,
        name: str,
        context: TraceContext,
        inputs: Iterable[Dict[str, Any]] | None = None,
        outputs: Iterable[Dict[str, Any]] | None = None,
        facets: Dict[str, Any] | None = None,
    ) -> Path:
        payload = {
            "eventType": name,
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "run": {
                "runId": f"{context.trace_id}-{context.lamport:016x}",
            },
            "job": {
                "namespace": "hyperion",
                "name": name,
            },
            "inputs": list(inputs or []),
            "outputs": list(outputs or []),
            "producer": "hyperion-fraud-stack",
            "schemaURL": f"https://openlineage.io/schemas/{self.schema_version}",
            "facets": facets or {},
        }
        path = self.directory / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return path

    def new_dataset(self, name: str, namespace: str = "hyperion") -> Dict[str, Any]:
        return {
            "namespace": namespace,
            "name": name,
            "facets": {
                "schema": {"fields": []},
            },
        }

    def run_facets(self, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        facets = {
            "sourceCodeLocation": {
                "type": "SourceCodeLocation",
                "url": "https://local/offline",
            },
            "nominalTime": {
                "type": "NominalTimeRunFacet",
                "nominalStartTime": datetime.now(timezone.utc).isoformat(),
            },
            "ownership": {
                "type": "OwnershipJobFacet",
                "owners": [
                    {"name": "fraud-platform", "type": "TEAM"},
                ],
            },
            "custom": extra or {},
        }
        return facets


def get_lineage_emitter() -> LineageEmitter:
    return LineageEmitter()

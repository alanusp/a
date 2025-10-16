"""State machine driver for dual-write cutovers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.migration import MigrationService, get_migration_service, MigrationPhase


def _load_actor(actor: str | None) -> str:
    if actor:
        return actor
    hostname = Path("/etc/hostname")
    if hostname.exists():
        return hostname.read_text().strip()
    return "migration-controller"


def main() -> None:
    parser = argparse.ArgumentParser(description="Dual-write cutover controller")
    parser.add_argument("action", choices=["start", "backfill", "validate", "commit", "finalize", "rollback"], help="State transition to execute")
    parser.add_argument("--actor", dest="actor", help="Controller identifier", default=None)
    args = parser.parse_args()
    actor = _load_actor(args.actor)
    service: MigrationService = get_migration_service()

    if args.action == "start":
        phase = service.begin_dual_write(actor)
    elif args.action == "backfill":
        phase = service.begin_backfill(actor)
    elif args.action == "validate":
        phase = service.mark_validate(actor)
    elif args.action == "finalize":
        phase = service.finalize(actor)
    elif args.action == "rollback":
        phase = service.rollback(actor)
    else:
        phase = service.commit_cutover(actor)

    status = service.status()
    print(json.dumps({"phase": phase.value if isinstance(phase, MigrationPhase) else phase, **status}, indent=2))


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from app.core.disk_guard import DiskGuard, DiskGuardError


def run_test(threshold: float) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        guard = DiskGuard(base_path=path)
        guard.soft_threshold = threshold
        try:
            guard.ensure_capacity(bytes_needed=1024, essential=False)
        except DiskGuardError:
            return True
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate low disk scenarios for DiskGuard")
    parser.add_argument("--threshold", type=float, default=0.9, help="Soft threshold to trigger")
    args = parser.parse_args()
    ok = run_test(args.threshold)
    if not ok:
        raise SystemExit("Disk guard did not trigger as expected")
    print("Disk guard refusal simulated successfully")


if __name__ == "__main__":
    main()

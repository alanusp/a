from __future__ import annotations

import json
import platform
import sys
from pathlib import Path


def run_checks() -> dict[str, object]:
    """Return a deterministic health snapshot used by the API doctor endpoint."""

    python_version = platform.python_version()
    site_packages = Path(sys.executable).resolve().parent.parent / "lib"
    checks = {
        "python_version": python_version,
        "executable": str(Path(sys.executable).resolve()),
        "site_packages_exists": site_packages.exists(),
        "lockfile_present": Path("requirements.lock").exists(),
    }
    checks["status"] = "ok" if all(checks.values()) else "warn"
    return checks


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(run_checks(), indent=2))

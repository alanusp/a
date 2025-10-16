from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def build_wheelhouse(requirements: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--dest",
            str(destination),
            "--requirement",
            str(requirements),
            "--no-deps",
        ],
        check=True,
        timeout=900,
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    requirements = repo_root / "requirements.lock"
    destination = repo_root / "vendor" / "wheels"
    build_wheelhouse(requirements, destination)


if __name__ == "__main__":
    main()

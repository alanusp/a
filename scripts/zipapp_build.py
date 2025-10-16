from __future__ import annotations

import os
import zipapp
from pathlib import Path


def build_zipapp(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1704067200")
    zipapp.create_archive(str(source), str(target), interpreter="/usr/bin/env python3", main="app.main:app")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    target = repo_root / "artifacts" / "api.pyz"
    build_zipapp(repo_root, target)
    print(f"created {target}")


if __name__ == "__main__":
    main()


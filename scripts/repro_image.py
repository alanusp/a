from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ARTIFACT = Path("artifacts/api.pyz")


def _build_once(tag: str) -> Path:
    env = os.environ.copy()
    env.setdefault("SOURCE_DATE_EPOCH", "1704067200")
    subprocess.run([sys.executable, "scripts/zipapp_build.py"], check=True, env=env)
    if not ARTIFACT.exists():
        raise SystemExit("zipapp build did not produce artifacts/api.pyz")
    tmpdir = Path(tempfile.mkdtemp(prefix="repro-build-"))
    target = tmpdir / f"api-{tag}.pyz"
    shutil.copy2(ARTIFACT, target)
    return target


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    first = _build_once("a")
    second = _build_once("b")
    first_hash = _digest(first)
    second_hash = _digest(second)
    report = {
        "first": str(first),
        "second": str(second),
        "first_hash": first_hash,
        "second_hash": second_hash,
        "match": first_hash == second_hash,
    }
    out_dir = Path("artifacts/repro")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if first_hash != second_hash:
        raise SystemExit("reproducibility check failed")
    print("Reproducible build confirmed", report)


if __name__ == "__main__":
    main()

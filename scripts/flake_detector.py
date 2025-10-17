from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

RUNS = int(os.getenv("FLAKE_RUNS", "3"))
PYTEST_ARGS = os.getenv("FLAKE_PYTEST_ARGS", "-q").split()


def main() -> None:
    failures: list[dict[str, object]] = []
    for run in range(1, RUNS + 1):
        seed = random.randint(0, 2**32 - 1)
        env = os.environ.copy()
        env.setdefault("PYTHONHASHSEED", str(seed))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *PYTEST_ARGS,
            ],
            env=env,
        )
        if result.returncode != 0:
            failures.append({"run": run, "seed": seed, "code": result.returncode})
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    report_path = out_dir / "flake_report.json"
    report_path.write_text(json.dumps({"failures": failures}, indent=2), encoding="utf-8")
    if failures:
        raise SystemExit("flaky tests detected")
    print(f"Completed {RUNS} runs with no flakes")


if __name__ == "__main__":
    main()

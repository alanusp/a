from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    env = os.environ.copy()
    env["HYPERION_FORCE_MUTATION"] = "1"
    try:
        subprocess.run(
            ["pytest", "tests/test_mutation_guard.py"],
            env=env,
            check=True,
            timeout=600,
        )
    except subprocess.CalledProcessError:
        print("Mutation killed")
        return 0
    except subprocess.TimeoutExpired:
        print("Mutation timed out", file=sys.stderr)
        return 1
    print("Mutation survived", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

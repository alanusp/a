from __future__ import annotations

import json
from pathlib import Path

from tomllib import loads


def main() -> None:
    pyproject = Path("pyproject.toml").read_text()
    data = loads(pyproject)
    dependencies = data["project"].get("dependencies", [])
    sbom = {
        "name": data["project"]["name"],
        "version": data["project"]["version"],
        "dependencies": dependencies,
    }
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    output = artifacts / "sbom.json"
    output.write_text(json.dumps(sbom, indent=2, sort_keys=True))
    print(f"SBOM written to {output}")


if __name__ == "__main__":
    main()

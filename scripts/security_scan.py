from __future__ import annotations

from pathlib import Path

from tomllib import loads


def main() -> None:
    pyproject = Path("pyproject.toml").read_text()
    data = loads(pyproject)
    dependencies = data["project"].get("dependencies", [])
    insecure = [dep for dep in dependencies if "==" not in dep]
    if insecure:
        raise SystemExit(f"Unpinned dependencies detected: {insecure}")
    print("Dependency pins verified")


if __name__ == "__main__":
    main()

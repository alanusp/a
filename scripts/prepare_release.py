from __future__ import annotations

from pathlib import Path


def main() -> None:
    artifacts = Path("artifacts")
    required = [artifacts / "sbom.json", artifacts / "signature.txt"]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"Missing release artifacts: {missing}")
    print("Release artifacts verified")


if __name__ == "__main__":
    main()

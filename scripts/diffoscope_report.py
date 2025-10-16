from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def _hash_path(path: Path) -> str:
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(path.iterdir()):
            digest.update(child.name.encode("utf-8"))
            digest.update(_hash_path(child).encode("utf-8"))
        return digest.hexdigest()
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def compare_artifacts(reference: Path, candidate: Path) -> list[str]:
    missing: list[str] = []
    for path in reference.rglob("*"):
        relative = path.relative_to(reference)
        other = candidate / relative
        if not other.exists():
            missing.append(f"missing:{relative}")
            continue
        if _hash_path(path) != _hash_path(other):
            missing.append(f"diff:{relative}")
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline diffoscope-lite")
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", default=Path("artifacts/repro/report.md"), type=Path)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    differences = compare_artifacts(args.reference, args.candidate)
    with args.output.open("w", encoding="utf-8") as handle:
        if not differences:
            handle.write("# Diffoscope Report\n\nNo differences detected.\n")
            return
        handle.write("# Diffoscope Report\n\n")
        handle.write("The following artifacts differ or are missing:\n")
        for entry in differences:
            handle.write(f"- {entry}\n")


if __name__ == "__main__":
    main()

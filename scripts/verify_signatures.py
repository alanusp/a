from __future__ import annotations

import hashlib
from pathlib import Path

SIGNATURE_FILE = Path("artifacts/signature.txt")
DEFAULT_TARGET = Path("artifacts/model_state_dict.json")


def _parse_signatures() -> dict[Path, str]:
    if not SIGNATURE_FILE.exists():
        raise SystemExit("signature file missing")
    mapping: dict[Path, str] = {}
    for raw in SIGNATURE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "=" in line:
            algo_part, path_part = line.split("=", 1)
            algo, digest = algo_part.split(":", 1)
            target = Path(path_part.strip())
        elif " " in line:
            algo_digest, path_str = line.split(" ", 1)
            algo, digest = algo_digest.split(":", 1)
            target = Path(path_str.strip())
        else:
            algo, digest = line.split(":", 1)
            target = DEFAULT_TARGET
        if algo.lower() != "sha256":
            raise SystemExit(f"Unsupported algorithm {algo}")
        mapping[target] = digest.strip()
    if DEFAULT_TARGET not in mapping:
        mapping[DEFAULT_TARGET] = mapping.get(DEFAULT_TARGET, "")
    return mapping


def _digest(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"artifact {path} missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    mismatches: list[str] = []
    for target, expected in _parse_signatures().items():
        if not expected:
            raise SystemExit(f"missing signature for {target}")
        actual = _digest(target)
        if actual != expected:
            mismatches.append(f"{target}: expected {expected} got {actual}")
    if mismatches:
        raise SystemExit("; ".join(mismatches))
    print("All signatures verified")


if __name__ == "__main__":
    main()

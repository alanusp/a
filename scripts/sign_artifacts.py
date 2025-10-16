from __future__ import annotations

import hashlib
from pathlib import Path


ARTIFACT = Path("artifacts/model_state_dict.json")
SIGNATURE_FILE = Path("artifacts/signature.txt")


def main() -> None:
    if not ARTIFACT.exists():
        raise SystemExit(f"Artifact {ARTIFACT} missing")
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    SIGNATURE_FILE.write_text(f"sha256:{digest}\n")
    print(f"Signature written to {SIGNATURE_FILE}")


if __name__ == "__main__":
    main()

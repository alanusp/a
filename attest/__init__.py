from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(slots=True)
class Attestation:
    subject: str
    materials: list[str]
    builder: str
    byproducts: dict[str, str]
    digest: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def create_attestation(
    *,
    subject: Path,
    materials: Iterable[Path],
    builder: str,
    byproducts: Mapping[str, str] | None = None,
    output: Path,
) -> Attestation:
    material_hashes = [
        f"{path.name}:{sha256(path.read_bytes()).hexdigest()}"
        for path in materials
        if path.exists()
    ]
    digest = sha256(subject.read_bytes()).hexdigest()
    attestation = Attestation(
        subject=str(subject),
        materials=sorted(material_hashes),
        builder=builder,
        byproducts=dict(byproducts or {}),
        digest=digest,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(attestation.to_json(), encoding="utf-8")
    return attestation


def verify_attestation(attestation_path: Path) -> bool:
    payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    subject = Path(payload["subject"])
    expected_digest = payload["digest"]
    if not subject.exists():
        return False
    digest = sha256(subject.read_bytes()).hexdigest()
    return digest == expected_digest

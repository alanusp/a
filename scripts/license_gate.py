from __future__ import annotations

import json
from pathlib import Path

import yaml


RULES_PATH = Path("security/rules/licenses.yml")
SBOM_PATH = Path("artifacts/sbom.json")


def load_rules() -> dict[str, set[str]]:
    if not RULES_PATH.exists():
        raise FileNotFoundError(RULES_PATH)
    with RULES_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    allowed = {item for item in payload.get("allowed", [])}
    disallowed = {item for item in payload.get("disallowed", [])}
    return {"allowed": allowed, "disallowed": disallowed}


def load_sbom() -> list[dict[str, str]]:
    if not SBOM_PATH.exists():
        raise FileNotFoundError(SBOM_PATH)
    with SBOM_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        components = payload.get("components", [])
    else:
        components = payload
    return [component for component in components if isinstance(component, dict)]


def enforce() -> None:
    rules = load_rules()
    allowed = rules["allowed"]
    disallowed = rules["disallowed"]
    offenders: list[str] = []
    for component in load_sbom():
        license_id = str(component.get("license", "")) or str(component.get("licenseConcluded", ""))
        name = component.get("name", "unknown")
        if license_id in disallowed:
            offenders.append(f"{name}:{license_id}")
        elif allowed and license_id not in allowed:
            offenders.append(f"{name}:{license_id or 'unknown'}")
    if offenders:
        raise SystemExit("disallowed licenses: " + ", ".join(offenders))


if __name__ == "__main__":
    enforce()

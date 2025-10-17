from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    TestClient = None  # type: ignore[assignment]


def _load_examples(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    examples: dict[str, dict[str, Any]] = {}
    for path, operations in spec.get("paths", {}).items():
        for method, details in operations.items():
            request_body = details.get("requestBody", {})
            content = request_body.get("content", {})
            example_payload = None
            if "application/json" in content:
                media = content["application/json"]
                if "example" in media:
                    example_payload = media["example"]
                elif "examples" in media:
                    example_payload = next(iter(media["examples"].values()))["value"]
            if example_payload is None:
                continue
            key = f"{method}:{path}"
            examples[key] = {"path": path, "method": method, "payload": example_payload}
    return examples


def _hash_response(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run(report: Path, approve: bool) -> int:
    if TestClient is None:
        print("FastAPI unavailable; skipping example validation")
        return 0
    from app.main import create_application  # noqa: WPS433

    app = create_application()
    client = TestClient(app)
    spec = app.openapi()
    examples = _load_examples(spec)
    hashes: dict[str, str] = {}

    for key, details in examples.items():
        path = details["path"]
        method = details["method"].upper()
        payload = details["payload"]
        response = client.request(method, path, json=payload)
        if response.status_code >= 400:
            raise AssertionError(f"example {key} failed with status {response.status_code}")
        hashes[key] = _hash_response(response.json())

    report.parent.mkdir(parents=True, exist_ok=True)
    if approve:
        report.write_text(json.dumps(hashes, indent=2), encoding="utf-8")
        print(f"approved {len(hashes)} OpenAPI examples")
        return 0

    if not report.exists():
        raise FileNotFoundError(f"baseline missing at {report}")

    baseline = json.loads(report.read_text(encoding="utf-8"))
    if baseline != hashes:
        diff = {
            "expected": baseline,
            "observed": hashes,
        }
        raise AssertionError(f"OpenAPI example hash drift: {json.dumps(diff, indent=2)}")
    print("OpenAPI examples validated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OpenAPI examples")
    parser.add_argument("--report", type=Path, default=Path("artifacts/golden/api_examples.json"))
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    return run(args.report, args.approve)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

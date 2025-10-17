from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings

SPEC_PATH = Path("artifacts/openapi/current.json")


def main() -> int:
    settings = get_settings()
    if not settings.api_deprecations:
        print("no deprecated endpoints configured")
        return 0
    if not SPEC_PATH.exists():
        print("missing OpenAPI spec at", SPEC_PATH)
        return 1
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    failures = []
    for path, _sunset in settings.api_deprecations.items():
        path_item = spec.get("paths", {}).get(path)
        if not path_item:
            failures.append(f"{path}: not present in OpenAPI spec")
            continue
        method_details = next(iter(path_item.values()))
        if not method_details.get("deprecated"):
            failures.append(f"{path}: missing deprecated flag")
        responses = method_details.get("responses", {})
        success = responses.get("200") or next(iter(responses.values()), {})
        headers = success.get("headers", {}) if isinstance(success, dict) else {}
        if "Deprecation" not in headers or "Sunset" not in headers:
            failures.append(f"{path}: missing Deprecation/Sunset headers in responses")
    if failures:
        print("Deprecation gate failures:")
        for issue in failures:
            print(" -", issue)
        return 1
    print("deprecation metadata ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

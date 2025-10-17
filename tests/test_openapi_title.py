import json
from pathlib import Path


def test_openapi_title_is_aegisflux() -> None:
    spec_path = Path("artifacts/openapi/current.json")
    assert spec_path.exists(), "OpenAPI spec missing"
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    assert data.get("info", {}).get("title") == "AegisFlux"

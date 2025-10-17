from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.gen_clients import generate_python_client, generate_ts_client


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("generated_client", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_generated_clients_round_trip(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_payload = {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.2.3"},
        "paths": {
            "/v1/predict": {
                "post": {
                    "operationId": "predict_transaction",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/TransactionPayload"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/PredictionResponse"}
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "TransactionPayload": {
                    "type": "object",
                    "properties": {"transaction_id": {"type": "string"}},
                    "required": ["transaction_id"],
                },
                "PredictionResponse": {
                    "type": "object",
                    "properties": {"transaction_id": {"type": "string"}},
                    "required": ["transaction_id"],
                },
            }
        },
    }
    spec_path.write_text(json.dumps(spec_payload), encoding="utf-8")

    python_out = tmp_path / "py"
    ts_out = tmp_path / "ts"
    generate_python_client(spec_payload, python_out)
    generate_ts_client(spec_payload, ts_out)

    import sys
    import types

    dummy_module = types.SimpleNamespace()

    class DummyInnerClient:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def request(self, method: str, path: str, params=None, json=None, headers=None):
            return DummyResponse({"transaction_id": "abc"})

        def close(self) -> None:  # pragma: no cover - interface compliance
            return None

    dummy_module.Client = DummyInnerClient
    sys.modules.setdefault("httpx", dummy_module)

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self, *_, **__):  # type: ignore[override]
            return self.__dict__

        @classmethod
        def model_validate(cls, payload):
            return cls(**payload)

    sys.modules.setdefault("pydantic", types.SimpleNamespace(BaseModel=DummyBaseModel))

    module = _load_module(python_out / "client.py")
    client = module.FraudApiClient(base_url="https://example")

    class DummyResponse:
        def __init__(self, payload: dict[str, str]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:  # pragma: no cover - compatibility
            return None

        def json(self) -> dict[str, str]:
            return self._payload

    request_model = module.TransactionPayload(transaction_id="abc")
    response = client.predict_transaction(request_model)
    assert response.transaction_id == "abc"
    assert client.version == "1.2.3"

    ts_content = (ts_out / "index.ts").read_text(encoding="utf-8")
    assert "version = '1.2.3'" in ts_content

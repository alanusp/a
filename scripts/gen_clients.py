#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "artifacts" / "openapi" / "current.json"
PY_CLIENT_ROOT = ROOT / "clients" / "python"
TS_CLIENT_ROOT = ROOT / "clients" / "ts"


@dataclass
class Schema:
    name: str
    payload: Dict[str, Any]

    def required(self) -> List[str]:
        value = self.payload.get("required", [])
        if isinstance(value, list):
            return [str(item) for item in value]
        return []


def _sanitize_name(name: str) -> str:
    sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    if keyword.iskeyword(sanitized):
        sanitized += "_"
    return sanitized or "unnamed"


def _python_type(schema: Dict[str, Any], *, components: Dict[str, Schema]) -> str:
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        return _sanitize_name(ref)
    schema_type = schema.get("type")
    if schema_type == "array":
        items = schema.get("items", {"type": "any"})
        return f"List[{_python_type(items, components=components)}]"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "string":
        if "enum" in schema:
            members = ", ".join(repr(v) for v in schema["enum"])
            return f"Literal[{members}]"
        return "str"
    if schema_type == "object":
        if "properties" in schema:
            return "Dict[str, Any]"
        return "Dict[str, Any]"
    return "Any"


def _ts_type(schema: Dict[str, Any], *, components: Dict[str, Schema]) -> str:
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        return _sanitize_name(ref)
    schema_type = schema.get("type")
    if schema_type == "array":
        items = schema.get("items", {"type": "unknown"})
        return f"{_ts_type(items, components=components)}[]"
    if schema_type == "integer" or schema_type == "number":
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "string":
        return "string"
    if schema_type == "object":
        return "Record<string, unknown>"
    return "unknown"


def _render_python_model(schema: Schema, components: Dict[str, Schema]) -> str:
    properties = schema.payload.get("properties", {})
    required = set(schema.required())
    lines = [f"class {_sanitize_name(schema.name)}(BaseModel):"]
    if not properties:
        lines.append("    pass")
        return "\n".join(lines)
    for prop_name, prop_schema in properties.items():
        py_name = _sanitize_name(prop_name)
        annotation = _python_type(prop_schema, components=components)
        default = "" if prop_name in required else " = None"
        lines.append(f"    {py_name}: {annotation}{default}")
    return "\n".join(lines)


def _render_ts_schema(schema: Schema, components: Dict[str, Schema]) -> str:
    properties = schema.payload.get("properties", {})
    required = set(schema.required())
    lines = [f"export const {_sanitize_name(schema.name)}Schema = z.object({{"]
    for prop_name, prop_schema in properties.items():
        ts_name = _sanitize_name(prop_name)
        schema_type = _ts_type(prop_schema, components=components)
        if "$ref" in prop_schema:
            ref = _sanitize_name(prop_schema["$ref"].split("/")[-1])
            expr = f"{ref}Schema"
        elif prop_schema.get("type") == "array" and "$ref" in prop_schema.get("items", {}):
            ref = _sanitize_name(prop_schema["items"]["$ref"].split("/")[-1])
            expr = f"z.array({ref}Schema)"
        else:
            mapping = {
                "string": "z.string()",
                "number": "z.number()",
                "integer": "z.number().int()",
                "boolean": "z.boolean()",
            }
            expr = mapping.get(prop_schema.get("type", ""), "z.any()")
        optional = "" if prop_name in required else ".optional()"
        lines.append(f"  {prop_name!r}: {expr}{optional},")
    lines.append("});")
    lines.append(f"export type {_sanitize_name(schema.name)} = z.infer<typeof {_sanitize_name(schema.name)}Schema>;")
    return "\n".join(lines)


def _operation_name(path: str, method: str, payload: Dict[str, Any]) -> str:
    if "operationId" in payload:
        return _sanitize_name(payload["operationId"])
    pieces = [method.lower()] + [segment for segment in path.strip("/").split("/") if segment]
    return _sanitize_name("_".join(pieces) or f"{method}_root")


def _collect_components(spec: Dict[str, Any]) -> Dict[str, Schema]:
    components = spec.get("components", {}).get("schemas", {})
    registry: Dict[str, Schema] = {}
    for name, payload in components.items():
        if isinstance(payload, dict):
            registry[name] = Schema(name=name, payload=payload)
    return registry


def generate_python_client(spec: Dict[str, Any], destination: Path) -> None:
    components = _collect_components(spec)
    destination.mkdir(parents=True, exist_ok=True)
    model_names = sorted(_sanitize_name(name) for name in components)
    all_export = ["'FraudApiClient'"] + [f"'{name}'" for name in model_names]
    models: List[str] = [
        "from typing import Any, Dict, List, Literal, Optional",
        "",
        "import httpx",
        "from pydantic import BaseModel",
        "",
        "__all__ = [" + ", ".join(all_export) + "]",
        "",
    ]
    for schema in sorted(components.values(), key=lambda item: item.name):
        models.append(_render_python_model(schema, components))
        models.append("")

    models.append(
        "class FraudApiClient:")
    models.append("    \"\"\"Typed httpx client generated from the project OpenAPI specification.\"\"\"")
    models.append("    def __init__(self, base_url: str, *, api_key: str | None = None, timeout: float = 10.0) -> None:")
    models.append("        self._base_url = base_url.rstrip('/')")
    models.append("        headers: Dict[str, str] = {}")
    models.append("        if api_key:")
    models.append("            headers['X-API-Key'] = api_key")
    models.append("        self._client = httpx.Client(base_url=self._base_url, headers=headers, timeout=timeout)")
    models.append("        self.version = spec_version")
    models.append("")
    models.append("    def close(self) -> None:")
    models.append("        self._client.close()")
    models.append("")
    models.append("    def _request(self, method: str, path: str, *, params: Dict[str, Any] | None = None, json_body: Any | None = None, headers: Dict[str, str] | None = None) -> httpx.Response:")
    models.append("        response = self._client.request(method, path, params=params, json=json_body, headers=headers)")
    models.append("        response.raise_for_status()")
    models.append("        return response")

    operations: List[str] = []
    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, payload in methods.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch"}:
                continue
            op_name = _operation_name(path, method, payload)
            params: List[str] = []
            param_serialization: List[str] = []
            query_params: List[str] = []
            path_params: List[str] = []
            header_params: List[str] = []
            for parameter in payload.get("parameters", []):
                if not isinstance(parameter, dict):
                    continue
                pname = parameter.get("name")
                if not pname:
                    continue
                ptype = parameter.get("schema", {"type": "string"})
                annotation = _python_type(ptype, components=components)
                default = "" if parameter.get("required") else " | None = None"
                params.append(f"{_sanitize_name(pname)}: {annotation}{default}")
                if parameter.get("in") == "query":
                    query_params.append(pname)
                    param_serialization.append(
                        f"        if {_sanitize_name(pname)} is not None: params['{pname}'] = {_sanitize_name(pname)}"
                    )
                elif parameter.get("in") == "path":
                    path_params.append(pname)
                elif parameter.get("in") == "header":
                    header_params.append(pname)
            request_body = payload.get("requestBody", {})
            body_annotation = "Any | None = None"
            body_var = None
            if isinstance(request_body, dict):
                content = request_body.get("content", {})
                json_schema = content.get("application/json", {}).get("schema")
                if json_schema:
                    body_annotation = _python_type(json_schema, components=components) + ""
                    params.append(f"payload: {body_annotation}")
                    body_var = "payload"
            responses = payload.get("responses", {})
            success_schema: Dict[str, Any] | None = None
            for status_code, details in responses.items():
                if str(status_code).startswith("2") and isinstance(details, dict):
                    success_schema = details.get("content", {}).get("application/json", {}).get("schema")
                    if success_schema:
                        break
            return_type = "httpx.Response"
            parse_line = "return response"
            if success_schema:
                annotation = _python_type(success_schema, components=components)
                return_type = annotation
                parse_line = f"        return {annotation}.model_validate(response.json())"
            signature = ["self"] + params
            operations.append(f"    def {op_name}(" + ", ".join(signature) + f") -> {return_type}:")
            operations.append("        params: Dict[str, Any] = {}")
            for line in param_serialization:
                operations.append(line)
            if path_params:
                fmt_path = path
                for pname in path_params:
                    fmt_path = fmt_path.replace(f"{{{pname}}}", f"{{{_sanitize_name(pname)}}}")
                operations.append(f"        path = f\"{fmt_path}\"")
            else:
                operations.append(f"        path = \"{path}\"")
            header_build: List[str] = []
            if header_params:
                operations.append("        headers: Dict[str, Any] = {}")
                for pname in header_params:
                    operations.append(
                        f"        if {_sanitize_name(pname)} is not None: headers['{pname}'] = {_sanitize_name(pname)}"
                    )
            else:
                operations.append("        headers = None")
            json_payload = body_var if body_var else "None"
            operations.append(
                f"        response = self._request('{method.upper()}', path, params=params or None, json_body={json_payload}, headers=headers)"
            )
            operations.append(parse_line)
            operations.append("")
    models.extend(operations)
    version = spec.get("info", {}).get("version", "0.0.0")
    preamble = [
        "\"\"\"Auto-generated client. Do not edit by hand.\"\"\"",
        "from __future__ import annotations",
        "",
        "spec_version = \"" + version + "\"",
        "",
    ]
    content = "\n".join(preamble + models)
    (destination / "client.py").write_text(content, encoding="utf-8")
    (destination / "__init__.py").write_text("from .client import *\n", encoding="utf-8")
    (destination / "README.md").write_text(
        f"""# Python Client\n\nThis directory contains the typed Python client for the Fraud API.\n\n* Version: `{version}`\n* Requirements: `httpx`, `pydantic`\n\n```python\nfrom clients.python import FraudApiClient, TransactionPayload\nclient = FraudApiClient(base_url=\"http://localhost:8000/v1\")\nresponse = client.post_v1_predict(TransactionPayload(transaction_id='t1'))\n```\n""",
        encoding="utf-8",
    )


def generate_ts_client(spec: Dict[str, Any], destination: Path) -> None:
    components = _collect_components(spec)
    destination.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [
        "// Auto-generated client. Do not edit by hand.",
        "import { z } from 'zod';",
        "",
    ]
    for schema in sorted(components.values(), key=lambda item: item.name):
        lines.append(_render_ts_schema(schema, components))
        lines.append("")
    lines.append("export interface ClientOptions { baseUrl: string; apiKey?: string; fetchImpl?: typeof fetch; }")
    lines.append("export class FraudApiClient {")
    lines.append("  readonly version = '" + spec.get("info", {}).get("version", "0.0.0") + "';")
    lines.append("  private readonly baseUrl: string;")
    lines.append("  private readonly apiKey?: string;")
    lines.append("  private readonly fetchImpl: typeof fetch;")
    lines.append("  constructor(options: ClientOptions) {")
    lines.append("    this.baseUrl = options.baseUrl.replace(/\\/$/, '');")
    lines.append("    this.apiKey = options.apiKey;")
    lines.append("    this.fetchImpl = options.fetchImpl ?? fetch;")
    lines.append("  }")
    lines.append("  private async request(path: string, init: RequestInit): Promise<Response> {")
    lines.append("    const headers = new Headers(init.headers);")
    lines.append("    if (this.apiKey) { headers.set('X-API-Key', this.apiKey); }")
    lines.append("    const response = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers });")
    lines.append("    if (!response.ok) { throw new Error(`Request failed with status ${response.status}`); }")
    lines.append("    return response;")
    lines.append("  }")
    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, payload in methods.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch"}:
                continue
            op_name = _operation_name(path, method, payload)
            request_schema = None
            body_schema = payload.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body_schema and "$ref" in body_schema:
                request_schema = _sanitize_name(body_schema["$ref"].split("/")[-1])
            response_schema = payload.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema")
            if response_schema and "$ref" in response_schema:
                response_schema = _sanitize_name(response_schema["$ref"].split("/")[-1])
            param_list = []
            param_init = []
            if request_schema:
                param_list.append(f"payload: {request_schema}")
                param_init.append("body: JSON.stringify(payload)")
            else:
                param_init.append("body: undefined")
            lines.append(f"  async {op_name}({', '.join(param_list)}) {{")
            body_fragment = ", ".join(param_init)
            request_line = "    const response = await this.request('{path}', {{ method: '{method}', headers: {{ 'Content-Type': 'application/json' }}, {body} }});".format(
                path=path,
                method=method.upper(),
                body=body_fragment,
            )
            lines.append(request_line)
            if response_schema:
                lines.append(
                    f"    const json = await response.json();\n    return {response_schema}Schema.parse(json);"
                )
            else:
                lines.append("    return response;")
            lines.append("  }")
    lines.append("}")
    (destination / "index.ts").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (destination / "README.md").write_text(
        """# TypeScript Client\n\nOffline-capable TypeScript bindings generated from the OpenAPI specification using Zod.\n""",
        encoding="utf-8",
    )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate typed clients from OpenAPI")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--python-out", type=Path, default=PY_CLIENT_ROOT)
    parser.add_argument("--ts-out", type=Path, default=TS_CLIENT_ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)

    spec_data = json.loads(args.spec.read_text(encoding="utf-8"))
    generate_python_client(spec_data, args.python_out)
    generate_ts_client(spec_data, args.ts_out)


if __name__ == "__main__":
    main()

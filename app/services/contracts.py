from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

try:
    from jsonschema import Draft202012Validator, ValidationError
except ModuleNotFoundError:  # pragma: no cover - fallback for offline environments
    class ValidationError(ValueError):
        pass

    class Draft202012Validator:  # type: ignore[override]
        def __init__(self, schema: Dict[str, Any]) -> None:
            self._schema = schema

        def validate(self, payload: Dict[str, Any]) -> None:
            required = self._schema.get("required", [])
            for field in required:
                if field not in payload:
                    raise ValidationError(f"Missing required field '{field}'")
            properties = self._schema.get("properties", {})
            for field, field_schema in properties.items():
                if field not in payload:
                    continue
                expected = field_schema.get("type")
                if expected is None:
                    continue
                if expected == "number" and not isinstance(payload[field], (int, float)):
                    raise ValidationError(f"Field '{field}' expected number")
                if expected == "string" and not isinstance(payload[field], str):
                    raise ValidationError(f"Field '{field}' expected string")


class JsonSchemaValidator:
    def __init__(self, schema: Dict[str, Any]) -> None:
        self._schema = schema
        self._validator = Draft202012Validator(schema)

    def validate(self, payload: Dict[str, Any]) -> None:
        self._validator.validate(payload)


@dataclass(slots=True)
class AvroField:
    name: str
    type: str


@dataclass(slots=True)
class AvroSchema:
    name: str
    namespace: str
    fields: list[AvroField]


class SchemaCompatibilityError(Exception):
    pass


class AvroRegistry:
    def __init__(self, schema_dir: Path) -> None:
        self.schema_dir = schema_dir
        self._cache: dict[str, AvroSchema] = {}

    def _load_raw(self, topic: str) -> dict[str, Any]:
        path = self.schema_dir / f"{topic}.avsc"
        if not path.exists():
            raise FileNotFoundError(f"Schema for topic '{topic}' not found at {path}")
        with path.open() as fp:
            return json.load(fp)

    def _parse(self, payload: dict[str, Any]) -> AvroSchema:
        if payload.get("type") != "record":
            raise ValueError("Only Avro record schemas are supported")
        fields = [
            AvroField(name=str(field["name"]), type=self._normalise_type(field["type"]))
            for field in payload["fields"]
        ]
        return AvroSchema(
            name=str(payload["name"]),
            namespace=str(payload.get("namespace", "")),
            fields=fields,
        )

    @staticmethod
    def _normalise_type(raw: Any) -> str:
        if isinstance(raw, list):
            return "union[" + ",".join(sorted(str(item) for item in raw)) + "]"
        return str(raw)

    def get(self, topic: str) -> AvroSchema:
        if topic not in self._cache:
            self._cache[topic] = self._parse(self._load_raw(topic))
        return self._cache[topic]

    def validate(self, topic: str, message: Dict[str, Any]) -> None:
        schema = self.get(topic)
        required = {field.name for field in schema.fields}
        missing = required - message.keys()
        if missing:
            raise ValidationError(f"Missing fields for {topic}: {sorted(missing)}")
        for field in schema.fields:
            value = message.get(field.name)
            if not self._value_matches_type(value, field.type):
                raise ValidationError(
                    f"Field '{field.name}' expected type '{field.type}', received '{type(value).__name__}'"
                )

    @staticmethod
    def _value_matches_type(value: Any, avro_type: str) -> bool:
        if avro_type == "string":
            return isinstance(value, str)
        if avro_type in {"double", "float"}:
            return isinstance(value, (int, float))
        if avro_type in {"long", "int"}:
            return isinstance(value, int)
        if avro_type == "boolean":
            return isinstance(value, bool)
        if avro_type.startswith("union"):
            for option in avro_type[len("union[") : -1].split(","):
                if AvroRegistry._value_matches_type(value, option):
                    return True
            return False
        return True

    def ensure_backward_compatible(self, topic: str, new_schema_payload: dict[str, Any]) -> None:
        current = self.get(topic)
        candidate = self._parse(new_schema_payload)
        current_fields = {field.name: field.type for field in current.fields}
        for name, type_ in current_fields.items():
            if name not in {field.name for field in candidate.fields}:
                raise SchemaCompatibilityError(f"Field '{name}' removed from schema")
            candidate_type = next(field.type for field in candidate.fields if field.name == name)
            if candidate_type != type_:
                raise SchemaCompatibilityError(
                    f"Field '{name}' type changed from '{type_}' to '{candidate_type}'"
                )

        # Additional fields must be optional (i.e., include null in a union)
        for field in candidate.fields:
            if field.name not in current_fields:
                if "null" not in field.type:
                    raise SchemaCompatibilityError(
                        f"New field '{field.name}' must allow null for backward compatibility"
                    )


class HttpContractValidator:
    def __init__(self, schema: Dict[str, Any]) -> None:
        self._validator = JsonSchemaValidator(schema)

    def __call__(self, payload: Dict[str, Any]) -> None:
        self._validator.validate(payload)


def load_json_schema(path: Path) -> Dict[str, Any]:
    with path.open() as fp:
        return json.load(fp)

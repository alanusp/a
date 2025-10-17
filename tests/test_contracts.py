from __future__ import annotations

from pathlib import Path

import pytest
from app.services.contracts import (
    AvroRegistry,
    JsonSchemaValidator,
    SchemaCompatibilityError,
    ValidationError,
)

SCHEMA_DIR = Path("schemas/avro")


def test_json_contract_accepts_valid_payload():
    schema = {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "string"},
            "amount": {"type": "number"},
        },
        "required": ["transaction_id", "amount"],
    }
    validator = JsonSchemaValidator(schema)
    validator.validate({"transaction_id": "txn-1", "amount": 42.0})


def test_avro_registry_validates_messages():
    registry = AvroRegistry(SCHEMA_DIR)
    valid = {
        "transaction_id": "t-1",
        "customer_id": "c-1",
        "merchant_id": "m-1",
        "amount": 10.0,
        "event_timestamp": 123456,
    }
    registry.validate("transactions.raw", valid)

    with pytest.raises(ValidationError):
        registry.validate("transactions.raw", {"transaction_id": "t-1"})


def test_backward_compatibility_checks():
    registry = AvroRegistry(SCHEMA_DIR)
    new_schema = {
        "type": "record",
        "name": "TransactionRaw",
        "namespace": "com.hyperion.fraud",
        "fields": [
            {"name": "transaction_id", "type": "string"},
            {"name": "customer_id", "type": "string"},
            {"name": "merchant_id", "type": "string"},
            {"name": "amount", "type": "double"},
            {"name": "event_timestamp", "type": "long"},
            {"name": "new_optional", "type": ["null", "string"], "default": None},
        ],
    }
    registry.ensure_backward_compatible("transactions.raw", new_schema)

    incompatible = {
        "type": "record",
        "name": "TransactionRaw",
        "namespace": "com.hyperion.fraud",
        "fields": [
            {"name": "transaction_id", "type": "int"},
        ],
    }
    with pytest.raises(SchemaCompatibilityError):
        registry.ensure_backward_compatible("transactions.raw", incompatible)

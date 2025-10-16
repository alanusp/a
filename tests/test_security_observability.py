from __future__ import annotations

from app.core.observability import AuditLogger, json_log, latency_exemplar, scrub_pii
from app.core.security import ApiKeyManager, ApiKeyRecord, ApiKeyStore, Role


def test_pii_scrubbing_masks_digits():
    masked = scrub_pii("card 12345678")
    assert masked.endswith("78")
    assert "1234" not in masked


def test_json_logging_includes_context_without_pii():
    log_line = json_log("customer 123456", context={"account": "987654"})
    assert "***" in log_line
    assert "987654" not in log_line


def test_latency_exemplar_includes_trace():
    exemplar = latency_exemplar(42.0, "trace-1")
    assert exemplar["latency_ms"] == 42.0
    assert exemplar["trace_id"] == "trace-1"


def test_audit_logger_masks_sensitive_fields():
    captured: list[str] = []
    logger = AuditLogger(captured.append)
    event = logger.log("rotate", actor="admin 123456", metadata={"key": "445566"})
    assert "***" in captured[0]
    assert "445566" not in captured[0]
    assert event.metadata["key"] == "445566"


def test_api_key_manager_roles():
    store = ApiKeyStore([ApiKeyRecord(key="viewer", role=Role.VIEWER)])
    manager = ApiKeyManager(store)
    allowed, _ = manager.authenticate({"X-API-Key": "viewer"})
    assert allowed is True
    allowed, _ = manager.authenticate(
        {"X-API-Key": "viewer"}, required_role=Role.OPERATOR
    )
    assert allowed is False
    store.insert("operator", Role.OPERATOR)
    allowed, _ = manager.authenticate(
        {"X-API-Key": "operator"}, required_role=Role.OPERATOR
    )
    assert allowed is True

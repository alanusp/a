from __future__ import annotations

from quality.expectations import DEFAULT_EXPECTATIONS


def test_expectations_detect_invalid_currency() -> None:
    result = DEFAULT_EXPECTATIONS.validate({
        "transaction_id": "txn-1",
        "amount": 10.0,
        "currency": "BTC",
    })
    assert not result.passed
    assert "currency outside allowed set" in result.failures[0]


def test_expectations_accept_valid_payload() -> None:
    result = DEFAULT_EXPECTATIONS.validate({
        "transaction_id": "txn-42",
        "amount": 10.0,
        "currency": "USD",
    })
    assert result.passed

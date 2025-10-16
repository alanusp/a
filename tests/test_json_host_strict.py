from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.hosts import enforce_allowed_host
from app.core.json_strict import JsonSafetyError, parse_money, strict_loads


def test_strict_json_rejects_nan():
    with pytest.raises(JsonSafetyError):
        strict_loads('{"value": NaN}')


def test_strict_json_depth_limit():
    payload = "0"
    for _ in range(20):
        payload = f'{{"a":{payload}}}'
    with pytest.raises(JsonSafetyError):
        strict_loads(payload, max_depth=10)


def test_money_precision():
    with pytest.raises(JsonSafetyError):
        parse_money("1.001")
    assert parse_money("12.34").quantize(parse_money("0.01")) == parse_money("12.34")


def test_allowed_hosts(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "example.com")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    enforce_allowed_host({"host": "example.com"})
    with pytest.raises(Exception):
        enforce_allowed_host({"host": "evil.com"})

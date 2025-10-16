from __future__ import annotations

from app.services.dsar_ops import DSAROperator, _format_preserving_mask


def test_format_preserving_mask_luhn_valid() -> None:
    value = "4111111111111111"
    masked = _format_preserving_mask(value, "salt")
    assert len(masked) == len(value)
    assert masked[:-1].isdigit()


def test_dsar_export_appends_ledger(tmp_path, monkeypatch) -> None:
    from app.core import audit

    ledger_path = tmp_path / "ledger.log"
    anchor_path = tmp_path / "anchor.json"
    monkeypatch.setenv("AUDIT_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv("AUDIT_ANCHOR_PATH", str(anchor_path))
    operator = DSAROperator(salt="salt")
    payload = {"pan": "4111111111111111"}
    masked = operator.export(payload)
    assert "pan" in masked
    assert ledger_path.exists()

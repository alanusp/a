from __future__ import annotations

from app.core.config import get_settings
from app.core.reload import get_reload_manager


def test_reload_detects_changes(monkeypatch, tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    anchor_path = tmp_path / "anchor.txt"
    monkeypatch.setenv("AUDIT_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv("AUDIT_ANCHOR_PATH", str(anchor_path))
    monkeypatch.setenv("PROJECT_NAME", "Before Reload")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    manager = get_reload_manager()
    manager.reload(dry_run=True)
    monkeypatch.setenv("PROJECT_NAME", "After Reload")
    result = manager.reload()
    assert "changed" in result
    assert result["changed"]["project_name"]["after"] == "After Reload"

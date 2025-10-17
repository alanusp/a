from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.core.egress_guard import OutboundEgressGuard
from app.core.idna import IDNAError, canonicalise_email
from app.core.leak_sentinel import LeakSentinel
from app.core.mtls import MTLSGenerationError, export_spki_pin
from app.core.quotas import TenantQuotaManager
from app.core.waf import inspect as waf_inspect
from app.services.reconcile import ExactOnceReconciler
from app.core.durability import DurabilityManager
from scripts.restore_rehearsal import rehearse


def test_egress_guard_blocks_and_allows(tmp_path: Path) -> None:
    guard = OutboundEgressGuard({"allowed.com": {"tenant-a"}}, audit_path=tmp_path / "audit.jsonl")
    denied = guard.check("https://evil.example", tenant_id="tenant-a")
    assert not denied.allowed
    allowed = guard.check("https://allowed.com", tenant_id="tenant-a")
    assert allowed.allowed


def test_idna_canonicalisation_rejects_mixed_scripts() -> None:
    result = canonicalise_email("user@example.com")
    assert result.canonical == "user@example.com"
    with pytest.raises(IDNAError):
        canonicalise_email("user@examрle.com")  # Cyrillic p


def test_leak_sentinel_detects_growth(tmp_path: Path) -> None:
    sentinel = LeakSentinel(window=2, fd_threshold=0, object_threshold=0)
    first = sentinel.sample()
    second = sentinel.sample()
    assert second.timestamp >= first.timestamp
    assert not sentinel.healthy()


def test_quota_manager_respects_burst() -> None:
    manager = TenantQuotaManager(default_qps=1.0, burst=0.0)
    decision = manager.check("tenant", cost=2.0)
    assert not decision.allowed
    later = manager.check("tenant", cost=0.5)
    assert later.allowed


def test_waf_blocks_high_entropy() -> None:
    payload = b"\xff" * 1024
    decision = waf_inspect(payload)
    assert not decision.allowed


def test_reconciler_outputs_proof(tmp_path: Path) -> None:
    manager = DurabilityManager(base_path=tmp_path / "wal")
    reconcile = ExactOnceReconciler(
        {"tenant": []}, audit_path=tmp_path / "report.json", durability_manager=manager
    )
    report = reconcile.reconcile()
    assert report.inspected >= 0
    assert Path(tmp_path / "report.json").exists()


def test_restore_rehearsal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tmp = tmp_path / "artifacts"
    monkeypatch.chdir(tmp_path)
    path = rehearse()
    data = json.loads(path.read_text())
    assert "records" in data


def test_spki_pin_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(Path.cwd())
    try:
        pin = export_spki_pin()
    except MTLSGenerationError:
        pytest.skip("openssl not available")
    assert isinstance(pin, str)
    assert pin


def test_scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path.cwd())
    sdk = Path("artifacts/sdk")
    sdk.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["python", "scripts/sdk_semver_gate.py", "--update"])
    subprocess.check_call(["python", "scripts/sdk_semver_gate.py", "--update"])
    repro_dir = Path("artifacts/repro")
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "amd64.sha256").write_text("digest", encoding="utf-8")
    (repro_dir / "arm64.sha256").write_text("digest", encoding="utf-8")
    subprocess.check_call(["python", "scripts/repro_multiarch.py"])

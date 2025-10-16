from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from app.core.crypto import build_ssl_context, ensure_ca, issue_certificate


def test_ca_generation_and_context(tmp_path):
    ca = ensure_ca(tmp_path)
    cert_path = tmp_path / "server.crt"
    key_path = tmp_path / "server.key"
    issue_certificate(ca=ca, common_name="localhost", cert_path=cert_path, key_path=key_path, san_hosts=["localhost"])
    context = build_ssl_context(ca=ca, cert_path=cert_path, key_path=key_path, server=True)
    assert context.verify_mode.value == 2  # ssl.CERT_REQUIRED
    assert Path(cert_path).exists()
    assert Path(key_path).exists()

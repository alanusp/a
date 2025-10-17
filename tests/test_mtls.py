from pathlib import Path

import pytest

from app.core import config
from app.core import mtls


def test_mtls_artifact_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config.get_settings.cache_clear()
    mtls.get_mtls_artifacts.cache_clear()
    monkeypatch.setenv("ENABLE_MTLS", "1")
    monkeypatch.setenv("MTLS_ARTIFACT_DIR", str(tmp_path))
    settings = config.get_settings()
    assert settings.enable_mtls is True
    artifacts = mtls.get_mtls_artifacts()
    for attr in ("ca_cert", "server_cert", "server_key", "client_cert", "client_key"):
        path = getattr(artifacts, attr)
        assert path.exists()
        assert path.is_file()

from __future__ import annotations

import stat
from pathlib import Path

from app.core.config import get_settings


class PermissionError(RuntimeError):
    pass


def _check_path(path: Path) -> None:
    if not path.exists():
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if path.is_dir():
        if mode & 0o077:
            path.chmod(0o700)
    else:
        if mode & 0o077:
            path.chmod(0o600)


def enforce_filesystem_permissions() -> None:
    settings = get_settings()
    critical_paths = [
        settings.base_wal_path,
        settings.privacy_salt_path,
        settings.dsar_dir,
        settings.audit_ledger_path,
        settings.key_manifest_path,
    ]
    for path in critical_paths:
        _check_path(Path(path))

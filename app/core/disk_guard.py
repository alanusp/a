from __future__ import annotations

import errno
import json
import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from app.core.config import get_settings


class DiskGuardError(RuntimeError):
    pass


class DiskGuard:
    def __init__(self, *, base_path: Optional[Path] = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.base_wal_path
        self.soft_threshold = float(os.getenv("DISK_SOFT_FREE_RATIO", "0.10"))
        self.hard_threshold = float(os.getenv("DISK_HARD_FREE_RATIO", "0.05"))
        self.status_path = Path("artifacts/disk_guard.json")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def free_ratio(self) -> float:
        usage = shutil.disk_usage(self.base_path)
        if usage.total == 0:
            return 1.0
        return usage.free / usage.total

    def ensure_capacity(
        self,
        *,
        bytes_needed: int,
        essential: bool,
        compactor: Optional[Callable[[], None]] = None,
    ) -> None:
        ratio = self.free_ratio()
        if ratio < self.hard_threshold:
            if compactor:
                compactor()
                ratio = self.free_ratio()
            if ratio < self.hard_threshold:
                raise DiskGuardError("disk hard limit reached")
        if ratio < self.soft_threshold and not essential:
            raise DiskGuardError("disk soft limit reached")
        self._write_status(ratio)

    def safe_append(
        self,
        path: Path,
        data: str,
        *,
        essential: bool,
        compactor: Optional[Callable[[], None]] = None,
    ) -> None:
        encoded = data.encode("utf-8")
        try:
            self.ensure_capacity(bytes_needed=len(encoded), essential=essential, compactor=compactor)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                if compactor:
                    compactor()
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                        return
                raise DiskGuardError("disk full during append") from exc
            raise

    def _write_status(self, ratio: float) -> None:
        payload = {
            "free_ratio": ratio,
            "soft_threshold": self.soft_threshold,
            "hard_threshold": self.hard_threshold,
        }
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


_GUARD: DiskGuard | None = None


def get_disk_guard() -> DiskGuard:
    global _GUARD
    if _GUARD is None:
        _GUARD = DiskGuard()
    return _GUARD

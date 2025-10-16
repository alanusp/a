from __future__ import annotations

import json
import tarfile
import time
from io import BytesIO
from pathlib import Path
from typing import Iterable

from app.core.cache import get_cache_registry
from app.core.limits import get_limit_registry
from app.core.startup import get_startup_state

DIAG_DIR = Path("artifacts/diag")
DEFAULT_FILES = (
    Path("artifacts/model_state_dict.json"),
    Path("artifacts/calibration.json"),
    Path("artifacts/limit_status.json"),
    Path("artifacts/schema_diff.json"),
)


def build_bundle(extra_files: Iterable[Path] | None = None) -> Path:
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    bundle_path = DIAG_DIR / f"diagnostics-{timestamp}.tar.gz"

    state = get_startup_state()
    metadata = {
        "generated_at": timestamp,
        "startup": {
            "ready": state.ready,
            "startup_time_ms": state.startup_time_ms,
        },
        "caches": get_cache_registry().summary(),
        "limits": get_limit_registry().status_snapshot(),
    }

    files = list(DEFAULT_FILES)
    if extra_files:
        files.extend(extra_files)

    with tarfile.open(bundle_path, "w:gz") as tar:
        payload = json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo("metadata.json")
        info.size = len(payload)
        tar.addfile(info, BytesIO(payload))
        for path in files:
            if path.exists():
                tar.add(path, arcname=path.name)
    return bundle_path

from __future__ import annotations

import faulthandler
import io
import threading
import time
from pathlib import Path


_DUMP_PATH = Path("artifacts/diag/thread_dump.txt")


def write_thread_dump() -> Path:
    """Capture a thread dump and lightweight heap summary."""

    _DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    buffer.write(f"# thread-dump {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    faulthandler.dump_traceback(file=buffer)
    buffer.write("\n# active-threads\n")
    for thread in threading.enumerate():
        buffer.write(f"- {thread.name} (daemon={thread.daemon})\n")
    _DUMP_PATH.write_text(buffer.getvalue(), encoding="utf-8")
    return _DUMP_PATH

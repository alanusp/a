from __future__ import annotations

import json
import os
from pathlib import Path

import redis


def restore(redis_url: str, source: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    payload = json.loads(source.read_text())
    client = redis.Redis.from_url(redis_url)
    with client.pipeline() as pipe:
        pipe.flushdb()
        for key, value in payload.items():
            pipe.set(key, value)
        pipe.execute()


def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    source = Path(os.getenv("REDIS_BACKUP", "artifacts/redis_backup.json"))
    restore(redis_url, source)
    print(f"redis restored from {source}")


if __name__ == "__main__":
    main()


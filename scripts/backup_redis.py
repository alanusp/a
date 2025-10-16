from __future__ import annotations

import json
import os
from pathlib import Path

import redis


def backup(redis_url: str, target: Path) -> None:
    client = redis.Redis.from_url(redis_url)
    payload: dict[str, str] = {}
    for key in client.scan_iter("*"):
        value = client.get(key)
        if value is None:
            continue
        payload[key.decode("utf-8")] = value.decode("utf-8", "ignore")
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))


def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    target = Path(os.getenv("REDIS_BACKUP", "artifacts/redis_backup.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    backup(redis_url, target)
    print(f"redis backup written to {target}")


if __name__ == "__main__":
    main()


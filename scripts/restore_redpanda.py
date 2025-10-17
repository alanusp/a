from __future__ import annotations

import json
import os
from pathlib import Path

from kafka import KafkaProducer


def restore(bootstrap: str, source: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    payload = json.loads(source.read_text())
    producer = KafkaProducer(bootstrap_servers=bootstrap, value_serializer=lambda v: v.encode("utf-8"))
    for topic, messages in payload.items():
        for record in messages:
            producer.send(topic, record.get("value", ""))
    producer.flush()


def main() -> None:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    source = Path(os.getenv("REDPANDA_BACKUP", "artifacts/redpanda_backup.json"))
    restore(bootstrap, source)
    print(f"redpanda restored from {source}")


if __name__ == "__main__":
    main()


from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from kafka import KafkaConsumer


TOPICS = ["transactions.scored", "transactions.raw"]


def consume(bootstrap: str, topics: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    consumer = KafkaConsumer(
        *topics,
        bootstrap_servers=bootstrap,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=1000,
        value_deserializer=lambda m: m.decode("utf-8", "ignore"),
    )
    payload: dict[str, list[dict[str, str]]] = {topic: [] for topic in topics}
    for message in consumer:
        payload[message.topic].append({"value": message.value, "partition": message.partition, "offset": message.offset})
    consumer.close()
    return payload


def main() -> None:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    target = Path(os.getenv("REDPANDA_BACKUP", "artifacts/redpanda_backup.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    data = consume(bootstrap, TOPICS)
    target.write_text(json.dumps(data, indent=2, sort_keys=True))
    print(f"redpanda backup written to {target}")


if __name__ == "__main__":
    main()


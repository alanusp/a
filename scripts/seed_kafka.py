from __future__ import annotations

import json
import random
import time
from typing import Iterable

from kafka import KafkaProducer

from app.core.config import get_settings


def generate_transactions(batch_size: int = 1) -> Iterable[dict[str, float | int | str]]:
    for _ in range(batch_size):
        amount = random.uniform(1.0, 1500.0)
        merchant_risk = random.random()
        velocity_1m = random.uniform(0, 10)
        yield {
            "transaction_id": f"txn_{int(time.time() * 1000)}_{random.randint(0, 999)}",
            "customer_id": f"cust_{random.randint(1, 1000)}",
            "merchant_id": f"mch_{random.randint(1, 100)}",
            "amount": round(amount, 2),
            "currency": random.choice(["USD", "EUR", "GBP", "JPY"]),
            "device_trust_score": round(random.uniform(0.3, 1.0), 3),
            "merchant_risk_score": round(merchant_risk, 3),
            "velocity_1m": round(velocity_1m, 3),
            "velocity_1h": round(random.uniform(0, 3), 3),
            "chargeback_rate": round(random.uniform(0, 0.4), 3),
            "account_age_days": round(random.uniform(30, 4000), 1),
            "customer_tenure": round(random.uniform(0.1, 15), 3),
            "geo_distance": round(random.uniform(0, 9000), 1),
        }


def main() -> None:
    settings = get_settings()
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        linger_ms=5,
    )

    try:
        while True:
            for payload in generate_transactions():
                producer.send(settings.kafka_topic, payload)
                print(f"Published {payload['transaction_id']}")
            producer.flush()
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Stopping event generator...")


if __name__ == "__main__":
    main()

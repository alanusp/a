from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, List, Tuple

BYTEWAX_AVAILABLE = True

try:  # pragma: no cover - exercised via integration environments
    from bytewax.connectors.kafka import KafkaInputConfig, KafkaOutputConfig
    from bytewax.dataflow import Dataflow
    from bytewax.operators import filter as wax_filter
    from bytewax.operators import map as wax_map
    from bytewax.operators.window import EventClockConfig, TumblingWindow
    from bytewax.outputs import StatelessSink
    from bytewax.testing import run_main
except ModuleNotFoundError:  # pragma: no cover - offline unit tests
    BYTEWAX_AVAILABLE = False
    KafkaInputConfig = KafkaOutputConfig = object  # type: ignore[assignment]

    class Dataflow:  # type: ignore[override]
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def input(self, *_: Any, **__: Any):
            def decorator(fn):
                return fn

            return decorator

    def wax_map(fn):  # type: ignore[override]
        return fn

    def wax_filter(fn):  # type: ignore[override]
        return fn

    class EventClockConfig:  # type: ignore[override]
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

    class TumblingWindow:  # type: ignore[override]
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def build(self, *_: Any, **__: Any):
            return lambda stream: stream

    class StatelessSink:  # type: ignore[override]
        pass

    def run_main(_: Any) -> None:  # type: ignore[override]
        raise RuntimeError("Bytewax runtime is unavailable in this environment")

from app.core.config import get_settings
from app.core.monitoring import report_metrics
from app.services.graph_features import get_graph_feature_service
from app.services.migration import get_migration_service
from app.core.units import quantize_prob


@dataclass
class AggregatedMetrics:
    window_start: datetime
    window_end: datetime
    avg_latency_ms: float
    fraud_rate: float
    volume: int


class RedisPredictionSink(StatelessSink):
    def __init__(self) -> None:
        from app.services.redis_stream import RedisStream

        self.redis_stream = RedisStream()

    def write_batch(self, batch: Iterable[Dict[str, Any]]) -> None:
        ordered = sorted(
            list(batch),
            key=lambda record: (
                record.get("payload", record).get("event_time")
                or record.get("payload", record).get("ingested_at")
                or "",
                hashlib.sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest(),
            ),
        )
        for item in ordered:
            dual_records = item.get("dual_write_records")
            if dual_records:
                for record in dual_records:
                    stream_key = f"{self.redis_stream.stream_key}.v{record['version']}"
                    self.redis_stream.publish(record, stream_key=stream_key)
                # Maintain legacy stream for baseline readers
                self.redis_stream.publish(dual_records[0], stream_key=self.redis_stream.stream_key)
            else:
                self.redis_stream.publish(item)


class RedisDeduplicator:
    def __init__(self, ttl_seconds: int = 120) -> None:
        self.ttl = ttl_seconds
        self._timestamps: Dict[str, float] = {}

    def _evict(self, now: float) -> None:
        expired = [key for key, ts in self._timestamps.items() if now - ts > self.ttl]
        for key in expired:
            del self._timestamps[key]

    def check_and_record(self, event_id: str, now: float) -> bool:
        self._evict(now)
        if event_id in self._timestamps:
            return False
        self._timestamps[event_id] = now
        return True


class BackpressureController:
    def __init__(self, max_records: int = 500) -> None:
        self._buffer: Deque[Dict[str, Any]] = deque()
        self.max_records = max_records

    def push(self, record: Dict[str, Any]) -> bool:
        if len(self._buffer) >= self.max_records:
            return False
        self._buffer.append(record)
        return True

    def drain(self) -> List[Dict[str, Any]]:
        drained = list(self._buffer)
        self._buffer.clear()
        return drained


settings = get_settings()
_deduper = RedisDeduplicator()
_backpressure = BackpressureController()

if BYTEWAX_AVAILABLE:
    dataflow = Dataflow("hyperion-stream")


def compose_event_id(payload: Dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(payload.get("transaction_id", "").encode())
    digest.update(payload.get("customer_id", "").encode())
    digest.update(payload.get("merchant_id", "").encode())
    digest.update(str(payload.get("amount", "")).encode())
    return digest.hexdigest()


def build_dual_write_records(base_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    settings = get_settings()
    migration = get_migration_service()
    versions: List[int] = [settings.scored_topic_version]
    if settings.dual_write_enabled:
        versions.append(settings.scored_topic_next_version)
    unique_versions: List[int] = []
    seen = set()
    for version in versions:
        if version in seen:
            continue
        seen.add(version)
        unique_versions.append(version)
    records: List[Dict[str, Any]] = []
    idem_key = base_payload.get("idempotency_key") or base_payload["event_id"]
    for version in unique_versions:
        candidate_payload = deepcopy(base_payload)
        candidate_payload["version"] = version
        checksum = migration.record_event(candidate_payload["event_id"], version, candidate_payload)
        records.append(
            {
                "event_id": candidate_payload["event_id"],
                "idempotency_key": idem_key,
                "version": version,
                "checksum": checksum,
                "payload": candidate_payload,
            }
        )
    return records


if BYTEWAX_AVAILABLE:

    @dataflow.input("kafka")
    def input_builder() -> KafkaInputConfig:
        return KafkaInputConfig(
            brokers=settings.kafka_bootstrap_servers.split(","),
            topic=settings.kafka_topic,
            tail=True,
            starting_offset="latest",
        )


def decode(event: Tuple[bytes, bytes]) -> Dict[str, Any]:
    key, value = event
    payload = json.loads(value.decode("utf-8"))
    payload["__event_key"] = key.decode("utf-8") if key else ""
    payload["ingested_at"] = datetime.utcnow().isoformat()
    payload["event_id"] = compose_event_id(payload)
    return payload


def enrich_with_prediction(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.routes import get_feature_service, get_inference_service

    feature_service = get_feature_service()
    inference_service = get_inference_service()
    graph_service = get_graph_feature_service()

    features = feature_service.to_feature_list(payload)
    result = inference_service.predict(features)

    payload["fraud_probability"] = quantize_prob(result.probability)
    payload["is_fraud"] = result.is_fraud
    payload["latency_ms"] = result.latency_ms
    payload["predicted_at"] = datetime.utcnow().isoformat()
    snapshot = inference_service.online_model.snapshot()
    weights = snapshot.get("weights", ["unknown"])
    payload["model_hash"] = str(weights[0]) if weights else "unknown"
    payload["graph_features"] = graph_service.update(
        event_id=payload["event_id"],
        payload=payload,
        fraud_probability=result.probability,
    )
    payload["dual_write_records"] = build_dual_write_records(deepcopy(payload))
    return payload


def deduplicate(payload: Dict[str, Any]) -> bool:
    return _deduper.check_and_record(payload["event_id"], datetime.utcnow().timestamp())


def apply_backpressure(payload: Dict[str, Any]) -> bool:
    return _backpressure.push(payload)


def in_latency_budget(payload: Dict[str, Any]) -> bool:
    return payload.get("latency_ms", 1e6) <= settings.latency_budget_ms


def to_window_key(payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    return payload["merchant_id"], payload


def compute_psi(baseline: List[float], challenger: List[float], bins: int = 10) -> float:
    if not baseline or not challenger:
        return 0.0
    combined = sorted(baseline + challenger)
    if len(combined) < 2:
        return 0.0
    edges = [combined[0] + (combined[-1] - combined[0]) * i / bins for i in range(bins + 1)]
    psi = 0.0
    for start, end in zip(edges[:-1], edges[1:]):
        base_count = sum(1 for value in baseline if start <= value <= end)
        cand_count = sum(1 for value in challenger if start <= value <= end)
        base_ratio = max(base_count / len(baseline), 1e-6)
        cand_ratio = max(cand_count / len(challenger), 1e-6)
        psi += (cand_ratio - base_ratio) * math.log(cand_ratio / base_ratio)
    return psi


def compute_ks(baseline: List[float], challenger: List[float]) -> float:
    if not baseline or not challenger:
        return 0.0
    baseline_sorted = sorted(baseline)
    challenger_sorted = sorted(challenger)
    cdf_base = [i / len(baseline_sorted) for i in range(1, len(baseline_sorted) + 1)]
    cdf_challenger = [i / len(challenger_sorted) for i in range(1, len(challenger_sorted) + 1)]
    max_len = max(len(cdf_base), len(cdf_challenger))
    cdf_base.extend([1.0] * (max_len - len(cdf_base)))
    cdf_challenger.extend([1.0] * (max_len - len(cdf_challenger)))
    return max(abs(a - b) for a, b in zip(cdf_base, cdf_challenger))


def build_metrics(window: Tuple[datetime, datetime], events: list[Dict[str, Any]]) -> AggregatedMetrics:
    if not events:
        return AggregatedMetrics(window[0], window[1], 0.0, 0.0, 0)
    latencies = [event["latency_ms"] for event in events]
    frauds = sum(1 for event in events if event["is_fraud"])
    avg_latency = report_metrics(latencies)["avg"]
    return AggregatedMetrics(
        window_start=window[0],
        window_end=window[1],
        avg_latency_ms=avg_latency,
        fraud_rate=frauds / len(events),
        volume=len(events),
    )


def metrics_to_dict(item: AggregatedMetrics) -> Dict[str, Any]:
    return {
        "window_start": item.window_start.isoformat(),
        "window_end": item.window_end.isoformat(),
        "avg_latency_ms": item.avg_latency_ms,
        "fraud_rate": item.fraud_rate,
        "volume": item.volume,
    }


def output_builder() -> StatelessSink:
    return RedisPredictionSink()


def kafka_metrics_sink_builder() -> KafkaOutputConfig:
    return KafkaOutputConfig(
        brokers=settings.kafka_bootstrap_servers.split(","),
        topic=f"{settings.kafka_topic}.metrics",
    )


if BYTEWAX_AVAILABLE:
    wire = (
        dataflow
        | "decode" >> wax_map(decode)
        | "dedupe" >> wax_filter(deduplicate)
        | "backpressure" >> wax_filter(apply_backpressure)
        | "predict" >> wax_map(enrich_with_prediction)
        | "latency_filter" >> wax_filter(in_latency_budget)
    )

    clock = EventClockConfig(lambda item: datetime.fromisoformat(item["predicted_at"]), wait_for_system_duration=1.0)
    window = TumblingWindow(length=5.0, align_to="event")

    metrics_stream = wire | "keyed" >> wax_map(to_window_key)
    metrics_stream = metrics_stream | "window" >> window.build(clock)
    metrics_stream = metrics_stream | "metrics" >> wax_map(lambda item: build_metrics(item[0], item[1]))
    metrics_stream | "metrics_to_redis" >> wax_map(metrics_to_dict) | "redis_sink" >> output_builder()
    metrics_stream | "metrics_to_kafka" >> wax_map(metrics_to_dict) | "kafka_sink" >> kafka_metrics_sink_builder()

    if __name__ == "__main__":
        run_main(dataflow)
else:
    if __name__ == "__main__":
        raise SystemExit("Bytewax runtime is unavailable in this environment")

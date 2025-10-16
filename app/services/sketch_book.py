from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from sketches.cms import CountMinSketch
from sketches.hll import HyperLogLog
from sketches.stable_bloom import StableBloomFilter
from app.core.limits import get_limit_registry, severity_score
from app.core.shutdown import get_shutdown_coordinator
from pathlib import Path
import base64
import json


@dataclass(slots=True)
class SketchBook:
    """Collection of probabilistic data structures for streaming telemetry."""

    width: int = 512
    depth: int = 5
    bloom_capacity: int = 2048
    bloom_hashes: int = 4
    cms: CountMinSketch = field(init=False)
    uniques: HyperLogLog = field(init=False)
    replay_filter: StableBloomFilter = field(init=False)

    def __post_init__(self) -> None:
        seeds = [7919 + idx * 1291 for idx in range(self.depth)]
        self.cms = CountMinSketch(width=self.width, depth=self.depth, seeds=seeds)
        self.uniques = HyperLogLog(precision=12)
        self.replay_filter = StableBloomFilter(
            capacity=self.bloom_capacity, hash_count=self.bloom_hashes, max_counter=5, decay=2
        )

    def observe(self, event_id: str, *, customer_id: str, device_id: str, merchant_id: str) -> Dict[str, float]:
        """Update sketches with the latest identifiers and return quick metrics."""

        registry = get_limit_registry()
        cardinality_cap = registry.for_resource("sketch_cardinality")
        estimate_before = int(self.uniques.estimate())
        decision_before = cardinality_cap.assess(estimate_before)
        if not decision_before.allowed:
            metrics = {
                "replay_flag": 1.0,
                "merchant_frequency_estimate": float(self.cms.estimate(f"merchant:{merchant_id}")),
                "device_frequency_estimate": float(self.cms.estimate(f"device:{device_id}")),
                "unique_customer_estimate": float(estimate_before),
                "sketch_limit_severity": severity_score("hard"),
            }
            return metrics

        self.cms.add(f"merchant:{merchant_id}")
        self.cms.add(f"device:{device_id}")
        self.uniques.add(customer_id)
        seen_before = event_id in self.replay_filter
        self.replay_filter.add(event_id)
        metrics = {
            "replay_flag": 1.0 if seen_before else 0.0,
            "merchant_frequency_estimate": float(self.cms.estimate(f"merchant:{merchant_id}")),
            "device_frequency_estimate": float(self.cms.estimate(f"device:{device_id}")),
            "unique_customer_estimate": float(self.uniques.estimate()),
        }
        decision_after = cardinality_cap.commit(int(metrics["unique_customer_estimate"]))
        metrics["sketch_limit_severity"] = severity_score(decision_after.severity)
        if decision_after.severity == "hard":
            metrics["sketch_limit_hard"] = 1.0
        elif decision_after.severity == "soft":
            metrics["sketch_limit_soft"] = 1.0
        return metrics

    def snapshot(self) -> Dict[str, bytes]:
        return {
            "cms": self.cms.to_bytes(),
            "hll": self.uniques.to_bytes(),
            "bloom": self.replay_filter.to_bytes(),
        }

    def load_snapshot(self, payload: Dict[str, bytes]) -> None:
        self.cms = CountMinSketch.from_bytes(payload["cms"])
        self.uniques = HyperLogLog.from_bytes(payload["hll"])
        self.replay_filter = StableBloomFilter.from_bytes(payload["bloom"])

    def persist(self, path: Path | None = None) -> Path:
        target = path or Path("artifacts/sketch_snapshot.json")
        snapshot = self.snapshot()
        serialised = {
            name: base64.b64encode(blob).decode("ascii") for name, blob in snapshot.items()
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(serialised, indent=2, sort_keys=True), encoding="utf-8")
        return target


_SKETCH_BOOK: SketchBook | None = None


def get_sketch_book() -> SketchBook:
    global _SKETCH_BOOK
    if _SKETCH_BOOK is None:
        _SKETCH_BOOK = SketchBook()
        get_shutdown_coordinator().register("sketch_snapshot", lambda timeout: _SKETCH_BOOK.persist())
    return _SKETCH_BOOK

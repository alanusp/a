from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Iterable, List


def _hashes(value: str, hash_count: int, capacity: int) -> Iterable[int]:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=16).digest()
    for idx in range(hash_count):
        start = (idx * 4) % len(digest)
        chunk = digest[start : start + 4]
        yield int.from_bytes(chunk, "big") % capacity


@dataclass(slots=True)
class StableBloomFilter:
    """Stable Bloom filter with bounded memory and false-positive rate."""

    capacity: int
    hash_count: int
    max_counter: int = 3
    decay: int = 1
    counters: List[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0 or self.hash_count <= 0:
            raise ValueError("capacity and hash_count must be positive")
        self.counters = [0] * self.capacity

    def add(self, value: str) -> None:
        positions = list(_hashes(value, self.hash_count, self.capacity))
        for _ in range(self.decay):
            victim = random.randrange(self.capacity)
            if self.counters[victim] > 0:
                self.counters[victim] -= 1
        for position in positions:
            self.counters[position] = self.max_counter

    def __contains__(self, value: str) -> bool:
        return all(self.counters[position] > 0 for position in _hashes(value, self.hash_count, self.capacity))

    def merge(self, others: Iterable["StableBloomFilter"]) -> "StableBloomFilter":
        for other in others:
            if other.capacity != self.capacity or other.hash_count != self.hash_count:
                raise ValueError("stable bloom filters must match shape")
            for idx, counter in enumerate(other.counters):
                self.counters[idx] = max(self.counters[idx], counter)
        return self

    def to_bytes(self) -> bytes:
        payload = bytearray()
        payload.extend(self.capacity.to_bytes(4, "big"))
        payload.extend(self.hash_count.to_bytes(2, "big"))
        payload.extend(self.max_counter.to_bytes(1, "big"))
        payload.extend(self.decay.to_bytes(1, "big"))
        for counter in self.counters:
            payload.extend(counter.to_bytes(1, "big"))
        return bytes(payload)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "StableBloomFilter":
        capacity = int.from_bytes(payload[0:4], "big")
        hash_count = int.from_bytes(payload[4:6], "big")
        max_counter = int.from_bytes(payload[6:7], "big")
        decay = int.from_bytes(payload[7:8], "big")
        instance = cls(capacity=capacity, hash_count=hash_count, max_counter=max_counter, decay=decay)
        instance.counters = [value for value in payload[8: 8 + capacity]]
        return instance

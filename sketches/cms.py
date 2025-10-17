from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass, field
from typing import Iterable, List


def _hash_with_seed(value: bytes, seed: int) -> int:
    digest = hashlib.blake2b(value, digest_size=16, person=seed.to_bytes(4, "big"))
    return int.from_bytes(digest.digest(), "big")


@dataclass(slots=True)
class CountMinSketch:
    """A compact frequency sketch with merge support and error bounds."""

    width: int
    depth: int
    seeds: List[int] | None = None
    _table: List[List[int]] = field(init=False, repr=False)
    _seeds: List[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.depth <= 0:
            raise ValueError("width and depth must be positive")
        self._table = [[0] * self.width for _ in range(self.depth)]
        if self.seeds is not None:
            if len(self.seeds) != self.depth:
                raise ValueError("seed count must match depth")
            self._seeds = list(self.seeds)
        else:
            rng = hashlib.blake2b(os.urandom(16), digest_size=16)
            base = int.from_bytes(rng.digest(), "big")
            self._seeds = [base + idx for idx in range(self.depth)]

    @property
    def epsilon(self) -> float:
        return math.e / self.width

    @property
    def delta(self) -> float:
        return math.exp(-self.depth)

    def add(self, key: str, count: int = 1) -> None:
        data = key.encode("utf-8")
        for row, seed in enumerate(self._seeds):
            column = _hash_with_seed(data, seed) % self.width
            self._table[row][column] += count

    def estimate(self, key: str) -> int:
        data = key.encode("utf-8")
        estimates = []
        for row, seed in enumerate(self._seeds):
            column = _hash_with_seed(data, seed) % self.width
            estimates.append(self._table[row][column])
        return min(estimates) if estimates else 0

    def merge(self, others: Iterable["CountMinSketch"]) -> "CountMinSketch":
        for other in others:
            if other.width != self.width or other.depth != self.depth:
                raise ValueError("sketch dimensions must match for merge")
            for row in range(self.depth):
                left_row = self._table[row]
                right_row = other._table[row]
                for column in range(self.width):
                    left_row[column] += right_row[column]
        return self

    def to_bytes(self) -> bytes:
        payload = bytearray()
        payload.extend(self.width.to_bytes(4, "big"))
        payload.extend(self.depth.to_bytes(4, "big"))
        for seed in self._seeds:
            payload.extend(seed.to_bytes(8, "big", signed=False))
        for row in self._table:
            for value in row:
                payload.extend(value.to_bytes(8, "big", signed=False))
        return bytes(payload)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "CountMinSketch":
        width = int.from_bytes(payload[0:4], "big")
        depth = int.from_bytes(payload[4:8], "big")
        instance = cls(width=width, depth=depth)
        offset = 8
        seeds: List[int] = []
        for _ in range(depth):
            seeds.append(int.from_bytes(payload[offset : offset + 8], "big"))
            offset += 8
        instance._seeds = seeds
        instance.seeds = list(seeds)
        for row in range(depth):
            for column in range(width):
                value = int.from_bytes(payload[offset : offset + 8], "big")
                offset += 8
                instance._table[row][column] = value
        return instance

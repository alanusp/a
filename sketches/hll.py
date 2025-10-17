from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable, List


def _hash(value: str) -> int:
    return int.from_bytes(hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(), "big")


@dataclass(slots=True)
class HyperLogLog:
    """Minimal HyperLogLog implementation supporting merges."""

    precision: int = 10
    registers: List[int] | None = None

    def __post_init__(self) -> None:
        if not 4 <= self.precision <= 16:
            raise ValueError("precision must be between 4 and 16")
        register_count = 1 << self.precision
        if self.registers is None:
            self.registers = [0] * register_count
        elif len(self.registers) != register_count:
            raise ValueError("register size does not match precision")

    @property
    def alpha(self) -> float:
        m = 1 << self.precision
        if m == 16:
            return 0.673
        if m == 32:
            return 0.697
        if m == 64:
            return 0.709
        return 0.7213 / (1 + 1.079 / m)

    def add(self, value: str) -> None:
        hashed = _hash(value)
        register_index = hashed >> (64 - self.precision)
        remaining = hashed << self.precision | (1 << (self.precision - 1))
        leading = self._rho(remaining, 64 - self.precision)
        assert self.registers is not None
        self.registers[register_index] = max(self.registers[register_index], leading)

    @staticmethod
    def _rho(value: int, bits: int) -> int:
        leading = 1
        for _ in range(bits):
            if value & (1 << (bits - 1)):
                break
            value <<= 1
            leading += 1
        return leading

    def estimate(self) -> float:
        assert self.registers is not None
        m = 1 << self.precision
        indicator = sum(2.0 ** -register for register in self.registers)
        raw_estimate = self.alpha * m * m / indicator
        zeros = self.registers.count(0)
        if raw_estimate <= 2.5 * m and zeros:
            return m * math.log(m / zeros)
        if raw_estimate > (1 << 32) / 30:
            return -((1 << 32) * math.log(1 - raw_estimate / (1 << 32)))
        return raw_estimate

    def merge(self, others: Iterable["HyperLogLog"]) -> "HyperLogLog":
        assert self.registers is not None
        for other in others:
            if other.precision != self.precision:
                raise ValueError("precision mismatch in HLL merge")
            assert other.registers is not None
            for idx, value in enumerate(other.registers):
                self.registers[idx] = max(self.registers[idx], value)
        return self

    def to_bytes(self) -> bytes:
        assert self.registers is not None
        payload = bytearray()
        payload.extend(self.precision.to_bytes(1, "big"))
        for register in self.registers:
            payload.extend(register.to_bytes(1, "big"))
        return bytes(payload)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "HyperLogLog":
        precision = int.from_bytes(payload[0:1], "big")
        registers = [value for value in payload[1:]]
        return cls(precision=precision, registers=registers)

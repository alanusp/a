from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, getcontext

getcontext().prec = 28


@dataclass(frozen=True)
class Milliseconds:
    value: int


def milliseconds(seconds: float) -> int:
    return int(round(seconds * 1_000))


def bytes_from_megabytes(megabytes: float) -> int:
    return int(megabytes * 1024 * 1024)


def quantize_prob(probability: float, digits: int = 6) -> float:
    quantizer = Decimal("1." + "0" * digits)
    return float(Decimal(str(probability)).quantize(quantizer, rounding=ROUND_HALF_EVEN))


def minor_units(amount: Decimal | float | str, exponent: int = 2) -> int:
    quantizer = Decimal(10) ** -exponent
    value = Decimal(str(amount)).quantize(quantizer, rounding=ROUND_HALF_EVEN)
    return int(value * (10 ** exponent))

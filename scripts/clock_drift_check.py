#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.trace import propagate_headers, start_trace


def run_check(simulated_offset: float = 0.0, tolerance: float = 0.05) -> bool:
    wall_start = time.time()
    mono_start = time.perf_counter()
    time.sleep(0.01)
    wall_delta = time.time() - wall_start + simulated_offset
    mono_delta = time.perf_counter() - mono_start
    if abs(wall_delta - mono_delta) > tolerance:
        return False
    first = start_trace({})
    second = start_trace(propagate_headers(first))
    return second.lamport > first.lamport


def main() -> None:
    parser = argparse.ArgumentParser(description="Check clock skew and Lamport monotonicity")
    parser.add_argument("--simulate-skew", type=float, default=0.0, help="Artificial skew delta in seconds")
    args = parser.parse_args()
    if not run_check(simulated_offset=args.simulate_skew):
        raise SystemExit("clock drift or Lamport regression detected")
    print("clock drift within tolerance")


if __name__ == "__main__":
    main()

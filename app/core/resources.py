from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CGROUP_BASE = Path("/sys/fs/cgroup")


@dataclass(slots=True)
class ResourceSnapshot:
    cpu_quota: float
    cpu_usage: float
    memory_limit: float
    memory_usage: float
    open_fds: int


def capture_snapshot(base: Path = CGROUP_BASE) -> ResourceSnapshot:
    cpu_max = base / "cpu.max"
    cpu_usage = base / "cpu.stat"
    memory_current = base / "memory.current"
    memory_max = base / "memory.max"

    quota = _parse_cpu_quota(cpu_max)
    usage = _parse_cpu_usage(cpu_usage)
    mem_limit = _parse_memory(memory_max)
    mem_usage = _parse_memory(memory_current)
    open_fds = len(os.listdir("/proc/self/fd"))
    return ResourceSnapshot(quota, usage, mem_limit, mem_usage, open_fds)


def _parse_cpu_quota(path: Path) -> float:
    try:
        with path.open("r", encoding="utf-8") as handle:
            content = handle.read().strip()
    except FileNotFoundError:
        return 0.0
    quota, period = content.split()
    if quota == "max":
        return float("inf")
    return float(quota) / max(float(period), 1.0)


def _parse_cpu_usage(path: Path) -> float:
    try:
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return 0.0
    for line in lines:
        if line.startswith("usage_usec"):
            _, value = line.split()
            return float(value)
    return 0.0


def _parse_memory(path: Path) -> float:
    try:
        with path.open("r", encoding="utf-8") as handle:
            content = handle.read().strip()
    except FileNotFoundError:
        return 0.0
    if content == "max":
        return float("inf")
    return float(content)

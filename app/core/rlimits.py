"""Resource limit enforcement."""
from __future__ import annotations

import os
import resource
from dataclasses import dataclass


@dataclass
class LimitConfig:
    nofile: int
    nproc: int
    address_space: int


class RLimitError(RuntimeError):
    pass


def _current(limit: int) -> int:
    soft, _ = resource.getrlimit(limit)
    return int(soft)


def enforce_limits(config: LimitConfig) -> None:
    targets = {
        resource.RLIMIT_NOFILE: config.nofile,
        resource.RLIMIT_NPROC: config.nproc,
        resource.RLIMIT_AS: config.address_space,
    }
    for key, value in targets.items():
        current = _current(key)
        if current < value:
            resource.setrlimit(key, (value, value))
        current = _current(key)
        if current < value:
            raise RLimitError(f"rlimit {key} below required {value}")


def load_from_env() -> LimitConfig:
    nofile = int(os.getenv("RLIMIT_NOFILE", "1024"))
    nproc = int(os.getenv("RLIMIT_NPROC", "512"))
    address_space = int(os.getenv("RLIMIT_AS", str(512 * 1024 * 1024)))
    return LimitConfig(nofile=nofile, nproc=nproc, address_space=address_space)

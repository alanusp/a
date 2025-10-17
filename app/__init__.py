from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported for typing only during analysis
    from fastapi import FastAPI


@lru_cache
def get_application() -> "FastAPI":
    """Return a lazily-instantiated FastAPI application.

    Importing ``fastapi`` has a non-trivial import graph that pulls in optional
    dependencies. Deferring the import keeps lightweight modules—such as unit
    tests exercising pure Python components—free from those requirements.
    """

    from .main import create_application

    return create_application()


__all__ = ["get_application"]

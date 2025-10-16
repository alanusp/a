from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class TaskSpec:
    name: str
    coroutine: Callable[[], Awaitable[T]]


class DeadlineTaskGroup:
    """Wrapper around :class:`asyncio.TaskGroup` with per-task deadlines."""

    def __init__(self, timeout: float | None = None) -> None:
        self._timeout = timeout
        self._group: asyncio.TaskGroup | None = None

    async def __aenter__(self) -> "DeadlineTaskGroup":
        self._group = asyncio.TaskGroup()
        await self._group.__aenter__()
        return self

    def create_task(self, coro: Awaitable[T], *, name: str | None = None) -> asyncio.Task[T]:
        if self._group is None:  # pragma: no cover - defensive
            raise RuntimeError("TaskGroup not started")
        if self._timeout is None:
            return self._group.create_task(coro, name=name)
        async def runner() -> T:
            return await asyncio.wait_for(coro, timeout=self._timeout)
        return self._group.create_task(runner(), name=name)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._group is None:  # pragma: no cover - defensive
            return
        await self._group.__aexit__(exc_type, exc, tb)


@asynccontextmanager
def run_tasks(tasks: Iterable[TaskSpec], *, timeout: float | None = None) -> Iterable[asyncio.Task[object]]:
    async with DeadlineTaskGroup(timeout=timeout) as group:
        created: list[asyncio.Task[object]] = []
        for spec in tasks:
            created.append(group.create_task(spec.coroutine(), name=spec.name))
        yield created

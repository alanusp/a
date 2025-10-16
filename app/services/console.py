from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Dict

from app.core.security import authorise_console


class ConsoleService:
    """In-memory publish/subscribe broker for console telemetry."""

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[dict[str, object]]" = asyncio.Queue(maxsize=1024)

    async def publish(self, payload: dict[str, object]) -> None:
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            await self._queue.get()
            self._queue.task_done()
            self._queue.put_nowait(payload)

    async def stream(self, headers: Dict[str, str]) -> AsyncIterator[str]:
        authorise_console(headers)
        while True:
            payload = await self._queue.get()
            yield f"data: {json.dumps(payload)}\n\n"
            self._queue.task_done()

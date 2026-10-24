"""In-process pub/sub feeding the SSE endpoint. Nothing is stored or queued without clients."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

DEFAULT_QUEUE_SIZE = 256
KEEPALIVE_S = 15.0

Event = tuple[str, dict[str, Any]]


class Subscription:
    def __init__(self, size: int) -> None:
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=size)
        # Set when the bus gave up on this client (full queue) or shut down.
        self.ended = False

    def _push(self, event: Event | None) -> bool:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            return False
        return True

    async def get(self, timeout: float) -> Event | None:
        """Next event, None on timeout. Raises StopAsyncIteration once ended and drained."""
        if self.ended and self._queue.empty():
            raise StopAsyncIteration
        try:
            event = await asyncio.wait_for(self._queue.get(), timeout)
        except TimeoutError:
            return None
        if event is None:
            raise StopAsyncIteration
        return event


class EventBus:
    """Fan out events to subscribers; a client that cannot keep up is dropped, never awaited."""

    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._size = queue_size
        self._subs: set[Subscription] = set()
        self._closed = False

    @property
    def has_subscribers(self) -> bool:
        return bool(self._subs)

    def subscribe(self) -> Subscription:
        sub = Subscription(self._size)
        if self._closed:
            sub.ended = True
        else:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subs.discard(sub)

    def publish(self, kind: str, data: dict[str, Any]) -> None:
        if not self._subs:
            return
        for sub in list(self._subs):
            if not sub._push((kind, data)):
                # The client reconnects and receives a fresh snapshot.
                sub.ended = True
                self._subs.discard(sub)

    def close(self) -> None:
        """End every stream so shutdown is not held up by open connections."""
        self._closed = True
        for sub in list(self._subs):
            sub.ended = True
            sub._push(None)
        self._subs.clear()


def format_sse(kind: str, data: dict[str, Any]) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def event_stream(
    bus: EventBus,
    snapshot: Callable[[], Awaitable[dict[str, Any]]],
    keepalive_s: float = KEEPALIVE_S,
) -> AsyncIterator[str]:
    """SSE text chunks: a full snapshot first, then live events and keepalive comments."""
    # Subscribe before the snapshot so no change falls in the gap between them.
    sub = bus.subscribe()
    try:
        yield format_sse("snapshot", await snapshot())
        while True:
            try:
                event = await sub.get(keepalive_s)
            except StopAsyncIteration:
                return
            yield ": keepalive\n\n" if event is None else format_sse(*event)
    finally:
        bus.unsubscribe(sub)

"""
SSE pub/sub for the automatic-trading activity feed (Window 2). Same
thread-to-asyncio bridge pattern as announcements/broadcaster.py -- kept as
a separate instance here since these are two different feeds; see
docs/requirements.md follow-up note about consolidating the shared
plumbing (not just the Kite session) into app/shared/ once touched again.
"""
import asyncio
import json
import threading
from typing import Any, Optional


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, item: dict[str, Any]) -> None:
        if self._loop is None:
            return
        with self._lock:
            subscribers = list(self._subscribers)
        if not subscribers:
            return
        payload = json.dumps(item, default=str)
        for q in subscribers:
            self._loop.call_soon_threadsafe(q.put_nowait, payload)


broadcaster = Broadcaster()

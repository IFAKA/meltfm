"""RadioState — observable state bridge between engine and WebSocket clients."""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RadioState:
    def __init__(self):
        self.radio_name: str = "default"
        self._subscribers: dict[str, asyncio.Queue] = {}

    def subscribe(self, client_id: str) -> asyncio.Queue:
        """Register a new client. Returns a queue that receives (event, data) tuples."""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers[client_id] = q
        return q

    def unsubscribe(self, client_id: str):
        self._subscribers.pop(client_id, None)

    @property
    def client_count(self) -> int:
        return len(self._subscribers)

    async def broadcast(self, event: str, data: Any):
        """Push an event to all connected clients."""
        dead = []
        for cid, q in self._subscribers.items():
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                # Client too slow — drop oldest
                try:
                    q.get_nowait()
                    q.put_nowait((event, data))
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    dead.append(cid)
        for cid in dead:
            self._subscribers.pop(cid, None)

    async def set_radio(self, name: str):
        self.radio_name = name

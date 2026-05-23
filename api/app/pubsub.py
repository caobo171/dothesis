import asyncio
import uuid
from collections import defaultdict


class InProcessPubsub:
    def __init__(self) -> None:
        self._subs: dict[uuid.UUID, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, key: uuid.UUID) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subs[key].append(q)
        return q

    def unsubscribe(self, key: uuid.UUID, q: asyncio.Queue) -> None:
        if q in self._subs.get(key, []):
            self._subs[key].remove(q)
        if not self._subs.get(key):
            self._subs.pop(key, None)

    async def publish(self, key: uuid.UUID, msg: dict) -> None:
        for q in list(self._subs.get(key, [])):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


pubsub = InProcessPubsub()

import asyncio
import json
from typing import AsyncIterator


def sse_pack(payload: dict, *, event_id: int | None = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append("data: " + json.dumps(payload))
    return "\n".join(parts) + "\n\n"


async def heartbeat_every(interval: float = 15.0) -> AsyncIterator[str]:
    while True:
        await asyncio.sleep(interval)
        yield ": keepalive\n\n"

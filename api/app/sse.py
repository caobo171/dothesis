import asyncio
import json
from typing import AsyncIterator


# Event types after which the job/run produces nothing further, so the SSE
# stream must end. Shared by both delivery paths (DB backlog replay and live
# pubsub) and by both streaming routers (jobs, runs) — a terminal event has to
# close the stream regardless of which path carried it or which router served
# it. Lives here, next to sse_pack, because that is the one module every SSE
# producer already imports; a per-router copy is how the paths drift apart.
TERMINAL_TYPES = {"job_done", "error"}

# Fields that may contain server-side diagnostic info (full Python tracebacks,
# internal stack info). Stripped from every SSE payload before transmission so
# they never reach a browser even though they remain in the DB for ops debugging.
SSE_REDACT_KEYS = {"traceback"}


def redact_for_sse(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in SSE_REDACT_KEYS}


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

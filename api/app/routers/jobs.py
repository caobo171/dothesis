import asyncio
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..job_runner import cancel_job, start_monitor
from ..models import Job, JobEvent, Paper, User
from ..pubsub import pubsub
from ..sse import sse_pack

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Fields that may contain server-side diagnostic info (full Python tracebacks,
# internal stack info). Stripped from every SSE payload before transmission so
# they never reach a browser even though they remain in the DB for ops debugging.
_SSE_REDACT_KEYS = {"traceback"}


def _redact_for_sse(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in _SSE_REDACT_KEYS}


def _owned_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "job not found"}})
    paper = db.get(Paper, j.paper_id)
    if not paper or paper.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "job not found"}})
    return j


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    j = _owned_job(db, user, job_id)
    return {
        "id": str(j.id), "paper_id": str(j.paper_id),
        "status": j.status, "phase": j.phase, "progress": j.progress,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "error_text": j.error_text,
    }


@router.post("/{job_id}/cancel", status_code=202)
def cancel(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(db_session)):
    j = _owned_job(db, user, job_id)
    if j.status in {"done", "failed", "canceled"}:
        return {"status": j.status}
    cancel_job(db, j)
    return {"status": "canceled"}


@router.get("/{job_id}/events")
async def stream_events(job_id: uuid.UUID, since: int = 0,
                        user: User = Depends(current_user), db: Session = Depends(db_session)):
    j = _owned_job(db, user, job_id)
    if j.status in {"queued", "running"}:
        start_monitor(job_id)

    backlog: list[tuple[int, dict]] = []
    events = db.scalars(
        select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id > since).order_by(JobEvent.id)
    ).all()
    for ev in events:
        # Spread meta_json first so column fields take precedence on key collisions.
        payload = {**(ev.meta_json or {}),
                   "type": ev.type, "phase": ev.phase, "agent": ev.agent, "text": ev.text}
        backlog.append((ev.id, _redact_for_sse(payload)))

    sub = pubsub.subscribe(job_id)

    async def gen() -> AsyncIterator[str]:
        try:
            for ev_id, payload in backlog:
                yield sse_pack(payload, event_id=ev_id)

            while True:
                try:
                    msg = await asyncio.wait_for(sub.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield sse_pack(_redact_for_sse({k: v for k, v in msg.items() if k != "id"}),
                                event_id=msg.get("id"))
                if msg.get("type") in {"job_done", "error"}:
                    break
        finally:
            pubsub.unsubscribe(job_id, sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

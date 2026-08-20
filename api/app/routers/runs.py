"""Runs router — start/pause/resume/status for auto-mode orchestrator runs."""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import job_runner
from ..auth_admin import readable_project
from ..db import db_session
from ..deps import current_user
from ..models import Job, JobEvent, Project, User
from ..pubsub import pubsub
from ..sse import TERMINAL_TYPES, redact_for_sse, sse_pack

router = APIRouter(tags=["runs"])


class StartRunBody(BaseModel):
    mode: str = Field("auto", pattern="^(auto)$")
    topic: str = Field(..., min_length=1)
    language: str | None = None
    citation_style: str | None = None


# POST-only read bodies. Filters that used to be query params now ride in the
# JSON body (the access_token rides there too, read by current_user) so no token
# ever lands in a URL. Extra fields (access_token) are ignored by pydantic.
class EstimateRunBody(BaseModel):
    topic: str = ""


class ListRunsBody(BaseModel):
    latest: bool = False
    limit: int = 50


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    return p


def _owned_run(db: Session, user: User, run_id: uuid.UUID) -> Job:
    j = db.get(Job, run_id)
    if not j or j.project_id is None:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, j.project_id)
    return j


@router.post("/projects/{project_id}/runs/estimate")
def estimate_run(project_id: uuid.UUID,
                 body: EstimateRunBody,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)):
    """Estimate token cost for an auto-mode run on this topic.

    Heuristic: ~3500 tokens per module × 5 modules = 17,500 baseline,
    plus 25 tokens per character of topic.
    """
    _owned_project(db, user, project_id)
    estimated = 17_500 + len(body.topic) * 25
    return {
        "estimated_tokens": estimated,
        "credit_balance": user.credit,
        "sufficient_credit": user.credit >= estimated,
    }


def _serialize_run(j: Job) -> dict:
    """Serialise a Job row to a dict for API responses."""
    return {
        "id": str(j.id),
        "project_id": str(j.project_id) if j.project_id else None,
        "status": j.status,
        "phase": j.phase,
        "progress": j.progress,
        "mode": j.mode,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


# Renamed from GET /projects/{id}/runs → POST .../runs/list: a POST .../runs
# already exists for starting a run, so the list read needs a distinct path.
@router.post("/projects/{project_id}/runs/list")
def list_runs(project_id: uuid.UUID,
              body: ListRunsBody,
              user: User = Depends(current_user),
              db: Session = Depends(db_session)):
    """List runs for a project. latest=true returns {run: <most-recent>} or {run: null}."""
    # Listing is read-only and powers the drawer on every workspace load.
    # Admin project inspection already uses an audited read policy elsewhere;
    # retaining the owner-only write guard here produced a noisy 404 poll while
    # the same admin could successfully read the project and thread.
    readable_project(db, user, project_id)
    latest = body.latest
    limit = body.limit
    # Order by started_at desc (NULLS LAST) so queued jobs that haven't started
    # yet sort after running/done jobs with real timestamps.
    q = (db.query(Job)
           .filter_by(project_id=project_id)
           .order_by(Job.started_at.desc().nulls_last()))

    if latest:
        row = q.first()
        return {"run": _serialize_run(row) if row else None}

    rows = q.limit(min(limit, 200)).all()
    return [_serialize_run(r) for r in rows]


@router.post("/projects/{project_id}/runs")
def start_run(project_id: uuid.UUID, body: StartRunBody,
              user: User = Depends(current_user),
              db: Session = Depends(db_session)):
    p = _owned_project(db, user, project_id)
    run = Job(
        paper_id=None,
        project_id=project_id,
        mode=body.mode,
        status="queued",
        langgraph_thread_id=str(uuid.uuid4()),
    )
    db.add(run); db.flush()
    # The deep agent is the only brain (2026-08-19 migration). `mode` is the
    # headless runner's own vocabulary — "auto" is the Job.mode column, which
    # the UI and admin screens still read, so the two must not be conflated.
    params = {
        "mode": "full_thesis",
        "topic": body.topic,
        "language": body.language or p.language,
        "citation_style": body.citation_style or p.citation_style,
    }
    job_runner.spawn_headless_run(db, run, params)
    db.commit()
    return {"run_id": str(run.id), "status": run.status}


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: uuid.UUID,
              user: User = Depends(current_user),
              db: Session = Depends(db_session)):
    run = _owned_run(db, user, run_id)
    if run.status not in {"queued", "running"}:
        return {"status": run.status}
    job_runner.cancel_job(db, run)
    return {"status": "pausing"}


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: uuid.UUID,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)):
    run = _owned_run(db, user, run_id)
    # Resume covers paused runs AND terminal-but-recoverable ones (failed /
    # canceled). There is no checkpoint to re-enter: the deep agent's durable
    # progress is whatever commit_slice wrote to the project store, so resuming
    # means running a FRESH agent over that state. Completed modules are intact;
    # a module that was in flight but never committed is redone.
    if run.status not in {"paused", "failed", "canceled"}:
        raise HTTPException(409,
                            detail={"error": {"code": "not_resumable",
                                              "message": f"run is {run.status}"}})
    # Clear the previous terminal markers so the resumed run reads as live.
    run.error_text = None
    run.finished_at = None
    job_runner.spawn_headless_run(db, run, {"mode": "full_thesis"})
    db.commit()
    return {"status": run.status}


@router.post("/runs/{run_id}")
def get_run(run_id: uuid.UUID,
            user: User = Depends(current_user),
            db: Session = Depends(db_session)):
    j = _owned_run(db, user, run_id)
    return {
        "id": str(j.id),
        "project_id": str(j.project_id) if j.project_id else None,
        "status": j.status, "phase": j.phase, "progress": j.progress,
        "mode": j.mode,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "error_text": j.error_text,
        "events_url": f"/api/v1/runs/{j.id}/events",
    }


@router.post("/runs/{run_id}/events")
async def stream_run_events(
    run_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """SSE stream of an auto-approve run's live progress.

    Runs are Job rows, so their events live in JobEvent + pubsub keyed by
    run_id — the same pipe job_runner._monitor writes to. POST (not GET) so the
    access_token rides in the body per this project's POST-only convention; the
    web client streams it via fetch + ReadableStream, not EventSource. We replay
    the backlog from the DB first (the drawer usually opens mid-run), then tail
    live events until a terminal one.
    """
    run = _owned_run(db, user, run_id)
    if run.status in {"queued", "running"}:
        job_runner.start_monitor(run_id)

    backlog: list[tuple[int, dict]] = []
    for ev in db.scalars(
        select(JobEvent).where(JobEvent.job_id == run_id).order_by(JobEvent.id)
    ).all():
        # meta_json first so the column fields win on key collisions.
        payload = {**(ev.meta_json or {}),
                   "type": ev.type, "phase": ev.phase, "agent": ev.agent, "text": ev.text}
        # meta_json is spread in verbatim and can carry a full server-side
        # traceback (job_runner stores one on failure for ops debugging). Redact
        # on the way out — the row keeps it, the browser never sees it.
        backlog.append((ev.id, redact_for_sse(payload)))

    sub = pubsub.subscribe(run_id)

    async def gen() -> AsyncIterator[str]:
        try:
            for ev_id, payload in backlog:
                yield sse_pack(payload, event_id=ev_id)
                # The run may have finished before the client ever connected, in
                # which case the terminal event arrives here (replayed from the
                # DB) and never through pubsub. Without this the generator fell
                # through to the loop below and emitted keepalives forever: a
                # stream for an already-finished run only ever closed because
                # the browser hung up, which leaks a task per reconnect and
                # hangs any client that waits for the response to end.
                if payload.get("type") in TERMINAL_TYPES:
                    return

            while True:
                try:
                    msg = await asyncio.wait_for(sub.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield sse_pack(redact_for_sse({k: v for k, v in msg.items() if k != "id"}),
                               event_id=msg.get("id"))
                if msg.get("type") in TERMINAL_TYPES:
                    break
        finally:
            pubsub.unsubscribe(run_id, sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: uuid.UUID,
               user: User = Depends(current_user),
               db: Session = Depends(db_session)):
    """Stop an in-flight auto-approve run (SIGTERM the subprocess, mark
    canceled). Distinct from pause/resume — there is no resume after cancel."""
    run = _owned_run(db, user, run_id)
    if run.status in {"done", "failed", "canceled"}:
        return {"status": run.status}
    job_runner.cancel_job(db, run)
    return {"status": "canceled"}

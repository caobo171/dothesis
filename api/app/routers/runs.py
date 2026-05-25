"""Runs router — start/pause/resume/status for auto-mode orchestrator runs."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import job_runner
from ..db import db_session
from ..deps import current_user
from ..models import Job, Project, User

router = APIRouter(tags=["runs"])


class StartRunBody(BaseModel):
    mode: str = Field("auto", pattern="^(auto)$")
    topic: str = Field(..., min_length=1)
    language: str | None = None
    citation_style: str | None = None


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
    brief = {
        "topic": body.topic,
        "language": body.language or p.language,
        "citation_style": body.citation_style or p.citation_style,
    }
    job_runner.spawn_orchestrator_run(db, run, brief)
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
    if run.status != "paused":
        raise HTTPException(409,
                            detail={"error": {"code": "not_paused",
                                              "message": f"run is {run.status}"}})
    job_runner.spawn_orchestrator_run(db, run, brief={}, resume_from=str(run.id))
    db.commit()
    return {"status": run.status}


@router.get("/runs/{run_id}")
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
        "events_url": f"/api/v1/jobs/{j.id}/events",
    }

"""Admin: list and cancel jobs across users."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..job_runner import cancel_job
from ..models import Job, Paper, User

router = APIRouter(prefix="/admin/jobs", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("")
def list_jobs(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: Session = Depends(db_session),
):
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    stmt = select(Job, Paper, User).join(Paper, Paper.id == Job.paper_id).join(User, User.id == Paper.user_id)
    if status:
        stmt = stmt.where(Job.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(desc(Job.started_at).nullslast()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(j.id), "paper_id": str(p.id), "paper_topic": p.topic,
                "owner_email": u.email, "status": j.status, "phase": j.phase,
                "progress": j.progress,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                "error_text": j.error_text,
            }
            for j, p, u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.post("/{job_id}/cancel", status_code=202)
def cancel(job_id: uuid.UUID, db: Session = Depends(db_session)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    if j.status in {"done", "failed", "canceled"}:
        return {"status": j.status}
    cancel_job(db, j)
    return {"status": "canceled"}

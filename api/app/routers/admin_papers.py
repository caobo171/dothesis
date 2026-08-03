"""Admin: list every thesis across all users.

Reads the `projects` table, NOT `papers`. `papers` is the legacy v1
generate-a-paper flow (still written only by routers/papers.py) and has been
empty since the v3 pivot — this endpoint used to select from it, so the admin
Papers screen showed "0 total" while `projects` held every real thesis. The
user-facing list (web/app/(inapp)/papers/page.tsx) had already moved to
/projects/list; this is the admin side catching up.

Column mapping, since Project has no academic_level/model_tier:
  topic  <- Project.name
  field  <- Project.field          (replaces LEVEL)
  module <- Project.focus or current_module   (replaces TIER)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..models import Project, User

router = APIRouter(prefix="/admin/papers", tags=["admin"], dependencies=[Depends(require_admin)])


# POST-only read: filters ride in the JSON body so no token/filter lands in a URL.
class ListPapersBody(BaseModel):
    page: int = 1
    page_size: int = 20
    status: str | None = None
    user_id: str | None = None
    # M1–M5. Filters on the same coalesce(focus, current_module) the list
    # returns, so what you filter by is what the MODULE column shows.
    module: str | None = None


@router.post("")
def list_papers(body: ListPapersBody, db: Session = Depends(db_session)):
    page = max(1, body.page)
    page_size = max(1, min(100, body.page_size))
    stmt = select(Project, User).join(User, User.id == Project.user_id)
    if body.status:
        stmt = stmt.where(Project.status == body.status)
    if body.user_id:
        stmt = stmt.where(Project.user_id == body.user_id)
    if body.module:
        module = body.module.upper()
        # focus is nullable and takes precedence when set, so "in M3" means
        # focus == M3, or focus is unset and current_module == M3.
        stmt = stmt.where(or_(
            Project.focus == module,
            (Project.focus.is_(None)) & (Project.current_module == module),
        ))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(desc(Project.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(p.id), "owner_email": u.email, "owner_id": str(u.id),
                "topic": p.name, "field": p.field,
                "module": p.focus or p.current_module, "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p, u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }

"""Admin: list all papers across users."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..models import Paper, User

router = APIRouter(prefix="/admin/papers", tags=["admin"], dependencies=[Depends(require_admin)])


# POST-only read: filters ride in the JSON body so no token/filter lands in a URL.
class ListPapersBody(BaseModel):
    page: int = 1
    page_size: int = 20
    status: str | None = None
    user_id: str | None = None


@router.post("")
def list_papers(body: ListPapersBody, db: Session = Depends(db_session)):
    page = max(1, body.page)
    page_size = max(1, min(100, body.page_size))
    status = body.status
    user_id = body.user_id
    stmt = select(Paper, User).join(User, User.id == Paper.user_id)
    if status:
        stmt = stmt.where(Paper.status == status)
    if user_id:
        stmt = stmt.where(Paper.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(desc(Paper.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(p.id), "owner_email": u.email, "owner_id": str(u.id),
                "topic": p.topic, "academic_level": p.academic_level,
                "model_tier": p.model_tier, "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p, u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }

"""Admin: users list, search, detail, grant credit."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..admin_config import is_super_admin
from ..auth_admin import require_admin
from ..credit_ledger import credit as ledger_credit, debit as ledger_debit, InsufficientCredit
from ..db import db_session
from ..models import User

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_admin)])


def _serialize(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "username": u.username,
        "credit": u.credit,
        "is_super_admin": is_super_admin(u),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


# POST-only reads: list filters ride in the JSON body (with the access_token,
# read by current_user via the router-level require_admin dep) so no token or
# filter ever lands in a URL. Extra fields (access_token) are ignored.
class ListUsersBody(BaseModel):
    page: int = 1
    page_size: int = 20
    q: str | None = None


@router.post("")
def list_users(body: ListUsersBody, db: Session = Depends(db_session)):
    page = max(1, body.page)
    page_size = max(1, min(100, body.page_size))
    q = body.q
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.username.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(desc(User.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_serialize(u) for u in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.post("/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(db_session)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    return _serialize(u)


class CreditGrantRequest(BaseModel):
    delta: int = Field(description="Positive = grant, negative = debit")
    note: str | None = None


@router.post("/{user_id}/credit")
def grant_credit(
    user_id: uuid.UUID,
    body: CreditGrantRequest,
    db: Session = Depends(db_session),
):
    if body.delta == 0:
        raise HTTPException(400, detail={"error": {"code": "zero_delta"}})
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    if body.delta > 0:
        ledger_credit(db, u, delta=body.delta, reason="admin_grant", ref_type="user", ref_id=u.id)
    else:
        try:
            ledger_debit(db, u, delta=-body.delta, reason="admin_grant", ref_type="user", ref_id=u.id)
        except InsufficientCredit as e:
            raise HTTPException(
                400,
                detail={"error": {"code": "insufficient", "balance": e.balance, "required": e.required}},
            )
    db.commit()
    db.refresh(u)
    return _serialize(u)

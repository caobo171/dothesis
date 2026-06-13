"""Admin: credit-purchase audit."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..models import Order, User

router = APIRouter(prefix="/admin/orders", tags=["admin"], dependencies=[Depends(require_admin)])


# POST-only read: filters ride in the JSON body so no token/filter lands in a URL.
class ListOrdersBody(BaseModel):
    page: int = 1
    page_size: int = 20
    status: str | None = None


@router.post("")
def list_orders(body: ListOrdersBody, db: Session = Depends(db_session)):
    page = max(1, body.page)
    page_size = max(1, min(100, body.page_size))
    status = body.status
    page_size = max(1, min(100, page_size))
    stmt = select(Order, User).join(User, User.id == Order.user_id)
    if status:
        stmt = stmt.where(Order.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(desc(Order.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(o.id), "owner_email": u.email, "owner_id": str(u.id),
                "package_id": o.package_id, "credits": o.credits,
                "amount_cents": o.amount_cents, "currency": o.currency,
                "status": o.status,
                "polar_checkout_id": o.polar_checkout_id,
                "polar_order_id": o.polar_order_id,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            }
            for o, u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }

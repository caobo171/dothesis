"""Credit packs, checkout, Polar webhook, and listings."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..credit_ledger import credit as ledger_credit
from ..db import db_session
from ..deps import current_user
from ..models import CreditTransaction, Order, User
from ..polar_client import PolarError, create_checkout, verify_webhook
from ..pricing import PACKAGES, PACKAGES_BY_ID
from ..settings import get_settings

router = APIRouter(prefix="/credit", tags=["credit"])


@router.post("/packages")
def packages():
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "price_cents": p["price_cents"],
            "old_price_cents": p["old_price_cents"],
            "credits": p["credits"],
        }
        for p in PACKAGES
    ]


class CheckoutRequest(BaseModel):
    package_id: str


@router.post("/checkout")
def checkout(
    body: CheckoutRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    pkg = PACKAGES_BY_ID.get(body.package_id)
    if not pkg:
        raise HTTPException(400, detail={"error": {"code": "bad_package", "message": "unknown package"}})

    order = Order(
        user_id=user.id,
        package_id=pkg["id"],
        credits=pkg["credits"],
        amount_cents=pkg["price_cents"],
        status="pending",
    )
    db.add(order)
    db.flush()

    settings = get_settings()
    return_url = f"{settings.opendraft_base_url}/credit?polar=success"
    cancel_url = f"{settings.opendraft_base_url}/credit?polar=cancel"
    try:
        checkout_id, url = create_checkout(order, return_url=return_url, cancel_url=cancel_url)
    except PolarError as e:
        raise HTTPException(502, detail={"error": {"code": "polar_failed", "message": str(e)}})

    order.polar_checkout_id = checkout_id
    db.commit()
    return {"checkout_url": url, "order_id": str(order.id)}


@router.post("/polar/webhook")
async def polar_webhook(
    request: Request,
    x_polar_signature: str | None = Header(default=None, alias="X-Polar-Signature"),
    db: Session = Depends(db_session),
):
    payload = await request.body()
    if not x_polar_signature:
        raise HTTPException(400, detail={"error": {"code": "missing_signature"}})
    try:
        verify_webhook(payload, x_polar_signature)
    except PolarError as e:
        raise HTTPException(400, detail={"error": {"code": "bad_signature", "message": str(e)}})

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, detail={"error": {"code": "bad_json"}})

    if event.get("type") != "order.paid":
        return {"ignored": event.get("type")}

    data = event.get("data") or {}
    checkout_id = data.get("checkout_id")
    polar_order_id = data.get("id")
    if not checkout_id:
        raise HTTPException(400, detail={"error": {"code": "no_checkout_id"}})

    order = db.scalar(select(Order).where(Order.polar_checkout_id == checkout_id))
    if not order:
        return {"ignored": "unknown_order"}
    if order.status == "paid":
        return {"ok": True, "already_paid": True}

    user = db.get(User, order.user_id)
    if not user:
        raise HTTPException(500, detail={"error": {"code": "user_gone"}})

    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)
    if polar_order_id:
        order.polar_order_id = polar_order_id

    ledger_credit(db, user, delta=order.credits, reason="purchase", ref_type="order", ref_id=order.id)

    db.commit()
    return {"ok": True}


@router.post("/orders")
def list_my_orders(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    rows = db.scalars(
        select(Order).where(Order.user_id == user.id).order_by(desc(Order.created_at)).limit(50)
    ).all()
    return [
        {
            "id": str(o.id),
            "package_id": o.package_id,
            "credits": o.credits,
            "amount_cents": o.amount_cents,
            "currency": o.currency,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        }
        for o in rows
    ]


@router.post("/transactions")
def list_my_transactions(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    rows = db.scalars(
        select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        .order_by(desc(CreditTransaction.id)).limit(200)
    ).all()
    return [
        {
            "id": r.id, "delta": r.delta, "reason": r.reason,
            "ref_type": r.ref_type, "ref_id": str(r.ref_id) if r.ref_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

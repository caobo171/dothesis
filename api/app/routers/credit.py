"""Credit packs, checkout, Polar webhook, and listings."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import paypal_client, sepay_client
from ..credit_ledger import credit as ledger_credit
from ..db import db_session
from ..deps import current_user
from ..models import CreditTransaction, Order, Project, Thread, User, sepay_code_seq
from ..polar_client import PolarError, create_checkout, verify_webhook
from ..pricing import PACKAGES, PACKAGES_BY_ID
from ..settings import get_settings

router = APIRouter(prefix="/credit", tags=["credit"])


def _grant_order(db: Session, order: Order, *, external_txn_id: str | None = None) -> bool:
    """Mark an order paid and credit the user — exactly once.

    Idempotent: returns False (no-op) if the order is already paid. Shared by
    every provider's success/webhook path so a re-delivered webhook or a
    capture-then-webhook race can't double-credit.
    """
    if order.status == "paid":
        return False
    user = db.get(User, order.user_id)
    if not user:
        raise HTTPException(500, detail={"error": {"code": "user_gone"}})
    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)
    if external_txn_id:
        order.external_txn_id = external_txn_id
    ledger_credit(db, user, delta=order.credits, reason="purchase",
                  ref_type="order", ref_id=order.id)
    return True


@router.post("/packages")
def packages():
    # VND is served alongside USD (not computed in the browser) so the price on
    # the card is the exact figure /sepay/intent will put in the QR — both come
    # from usd_cents_to_vnd. A client-side conversion would drift from the
    # backend on rounding and on any USD_TO_VND change the page hasn't reloaded
    # for, and a VN student would see one amount and be asked to transfer another.
    settings = get_settings()
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "price_cents": p["price_cents"],
            "old_price_cents": p["old_price_cents"],
            "price_vnd": sepay_client.usd_cents_to_vnd(p["price_cents"], settings),
            "old_price_vnd": sepay_client.usd_cents_to_vnd(p["old_price_cents"], settings),
            "credits": p["credits"],
        }
        for p in PACKAGES
    ]


class CheckoutRequest(BaseModel):
    package_id: str


class OrderStatusRequest(BaseModel):
    order_id: str


def _as_uuid(s: str):
    import uuid as _uuid
    try:
        return _uuid.UUID(str(s))
    except (ValueError, TypeError):
        raise HTTPException(400, detail={"error": {"code": "bad_id"}})


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
    return_url = f"{settings.dothesis_base_url}/credit?polar=success"
    cancel_url = f"{settings.dothesis_base_url}/credit?polar=cancel"
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
    if polar_order_id:
        order.polar_order_id = polar_order_id
    granted = _grant_order(db, order, external_txn_id=polar_order_id)
    db.commit()
    return {"ok": True, "already_paid": not granted}


@router.post("/methods")
def payment_methods():
    """Which providers the frontend should offer.

    `sepay` is listed only when configured; the frontend additionally gates it
    to UTC+7 users. Polar/PayPal availability follows DOTHESIS_PAYMENTS (and
    dummy mode keeps everything on for local dev).
    """
    settings = get_settings()
    configured = {p.strip() for p in settings.dothesis_payments.split(",") if p.strip()}
    dummy = settings.dothesis_payments == "dummy"
    methods = []
    if dummy or "polar" in configured:
        methods.append("polar")
    if dummy or "paypal" in configured or settings.paypal_client_id:
        methods.append("paypal")
    sepay_on = dummy or sepay_client.is_enabled(settings)
    if sepay_on:
        methods.append("sepay")
    return {"methods": methods, "sepay_enabled": sepay_on}


# --- PayPal ----------------------------------------------------------------

@router.post("/paypal/create-order")
def paypal_create_order(
    body: CheckoutRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    pkg = PACKAGES_BY_ID.get(body.package_id)
    if not pkg:
        raise HTTPException(400, detail={"error": {"code": "bad_package", "message": "unknown package"}})
    order = Order(
        user_id=user.id, package_id=pkg["id"], credits=pkg["credits"],
        amount_cents=pkg["price_cents"], status="pending", provider="paypal",
    )
    db.add(order)
    db.flush()
    settings = get_settings()
    try:
        paypal_order_id, approve_url = paypal_client.create_order(
            order,
            return_url=f"{settings.dothesis_base_url}/credit/paypal-return",
            cancel_url=f"{settings.dothesis_base_url}/credit?paypal=cancel",
        )
    except paypal_client.PayPalError as e:
        raise HTTPException(502, detail={"error": {"code": "paypal_failed", "message": str(e)}})
    order.paypal_order_id = paypal_order_id
    db.commit()
    return {"approval_url": approve_url, "order_id": str(order.id), "paypal_order_id": paypal_order_id}


class PayPalCaptureRequest(BaseModel):
    paypal_order_id: str


@router.post("/paypal/capture")
def paypal_capture(
    body: PayPalCaptureRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Return handler: capture the approved order and grant credits.

    Both this and the webhook grant via _grant_order, so whichever lands first
    wins and the other is a no-op.
    """
    order = db.scalar(select(Order).where(Order.paypal_order_id == body.paypal_order_id))
    if not order or order.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    if order.status == "paid":
        return {"ok": True, "already_paid": True}
    try:
        status, capture_id = paypal_client.capture_order(body.paypal_order_id)
    except paypal_client.PayPalError as e:
        raise HTTPException(502, detail={"error": {"code": "paypal_failed", "message": str(e)}})
    if status != "COMPLETED":
        raise HTTPException(402, detail={"error": {"code": "not_completed", "message": status}})
    _grant_order(db, order, external_txn_id=capture_id)
    db.commit()
    return {"ok": True}


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request, db: Session = Depends(db_session)):
    payload = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        paypal_client.verify_webhook(headers, payload)
    except paypal_client.PayPalError as e:
        raise HTTPException(400, detail={"error": {"code": "bad_signature", "message": str(e)}})
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, detail={"error": {"code": "bad_json"}})
    if event.get("event_type") != "PAYMENT.CAPTURE.COMPLETED":
        return {"ignored": event.get("event_type")}
    resource = event.get("resource") or {}
    order_id = resource.get("custom_id")
    capture_id = resource.get("id")
    if not order_id:
        return {"ignored": "no_custom_id"}
    order = db.get(Order, _as_uuid(order_id))
    if not order:
        return {"ignored": "unknown_order"}
    granted = _grant_order(db, order, external_txn_id=capture_id)
    db.commit()
    return {"ok": True, "already_paid": not granted}


# --- SePay (VietQR bank transfer, package-based) ----------------------------

@router.post("/sepay/intent")
def sepay_intent(
    body: CheckoutRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Create a pending SePay order and return the VietQR + bank details."""
    settings = get_settings()
    if not sepay_client.is_enabled(settings) and settings.dothesis_payments != "dummy":
        raise HTTPException(400, detail={"error": {"code": "sepay_disabled"}})
    pkg = PACKAGES_BY_ID.get(body.package_id)
    if not pkg:
        raise HTTPException(400, detail={"error": {"code": "bad_package", "message": "unknown package"}})
    amount_vnd = sepay_client.usd_cents_to_vnd(pkg["price_cents"], settings)
    order = Order(
        user_id=user.id, package_id=pkg["id"], credits=pkg["credits"],
        amount_cents=pkg["price_cents"], currency="VND", status="pending",
        provider="sepay", amount_vnd=amount_vnd,
    )
    db.add(order)
    db.flush()
    memo = sepay_client.order_memo(db.scalar(sepay_code_seq), settings)
    order.sepay_memo = memo
    db.commit()
    # `memo` is the bare code we match webhooks on; `transfer_content` is what
    # the payer types — the two differ on the shared VietinBank rail, and the QR
    # has to carry the latter or the money never reaches our sub-account.
    content = sepay_client.transfer_content(memo, settings)
    return {
        "order_id": str(order.id),
        "memo": memo,
        "transfer_content": content,
        "amount_vnd": amount_vnd,
        "qr_url": sepay_client.qr_image_url(content, amount_vnd, settings),
        "bank_code": settings.sepay_bank_code,
        "bank_name": sepay_client.bank_display_name(settings),
        "account_number": settings.sepay_account_number,
    }


def sepay_webhook_path(settings=None) -> str:
    """Leading-slash path for the SePay webhook, below the /api/v1 prefix.

    Read from settings rather than hardcoded so the path can be rotated with an
    env change instead of a code change, and so the value actually used in prod
    never lands in the repo. Tests and any ops tooling should call this instead
    of writing the path out, so a rotation can't leave them behind.
    """
    settings = settings or get_settings()
    return "/" + settings.sepay_webhook_path.strip("/")


def mount_sepay_webhook(app, prefix: str = "/api/v1") -> None:
    """Register the webhook at its configured path.

    Done here, at app construction, rather than with a @router decorator: a
    decorator binds its path at import time, which would freeze whatever
    SEPAY_WEBHOOK_PATH happened to be set when the module first loaded.
    """
    app.add_api_route(
        f"{prefix}{sepay_webhook_path()}",
        sepay_webhook,
        methods=["POST"],
        tags=["credit"],
        include_in_schema=False,  # keep the path out of /docs and openapi.json
    )


async def sepay_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(db_session),
):
    """SePay calls this when a bank transfer is received.

    Mounted by mount_sepay_webhook() at the unguessable SEPAY_WEBHOOK_PATH, not
    at a predictable /sepay/webhook. Auth: `Authorization: Apikey <SEPAY_API_KEY>`,
    checked before the body is read so unauthorized traffic costs nothing. Only
    inbound transfers whose content carries one of our memos are credited, once,
    by the exact amount due.
    """
    settings = get_settings()
    if settings.dothesis_payments != "dummy":
        expected = f"Apikey {settings.sepay_api_key}"
        if not settings.sepay_api_key or authorization != expected:
            raise HTTPException(401, detail={"error": {"code": "bad_apikey"}})
    payload = await request.body()
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, detail={"error": {"code": "bad_json"}})

    if (event.get("transferType") or "").lower() != "in":
        return {"ignored": "not_inbound"}
    ref = str(event.get("referenceCode") or event.get("id") or "")
    if ref and db.scalar(select(Order).where(Order.external_txn_id == ref)):
        return {"ok": True, "already_paid": True}  # duplicate delivery

    content = event.get("code") or event.get("content") or event.get("description") or ""
    candidates = sepay_client.memo_candidates(content, settings)
    if not candidates:
        # Not ours. Expected traffic, not an error: this account is shared with
        # other brands (Fillform's FFV codes), whose transfers we must ignore.
        return {"ignored": "no_memo"}
    order = next(
        (o for o in (db.scalar(select(Order).where(Order.sepay_memo == c)) for c in candidates) if o),
        None,
    )
    if not order:
        return {"ignored": "unknown_order"}

    # Guard against underpayment: require the transferred amount to cover the
    # order's VND price (allow a small rounding tolerance).
    transferred = int(float(event.get("transferAmount") or 0))
    if order.amount_vnd and transferred + 1 < order.amount_vnd:
        return {"ignored": "underpaid", "expected": order.amount_vnd, "got": transferred}

    granted = _grant_order(db, order, external_txn_id=ref or None)
    db.commit()
    return {"ok": True, "already_paid": not granted}


@router.post("/order/status")
def order_status(
    body: OrderStatusRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Single-order status — the SePay/PayPal frontends poll this."""
    order = db.get(Order, _as_uuid(body.order_id))
    if not order or order.user_id != user.id:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    return {"order_id": str(order.id), "status": order.status,
            "credits": order.credits, "provider": order.provider}


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

    # Enrich thread-scoped rows (chat_turn) with their project + names so the
    # UI can deep-link each spend back to the conversation that incurred it.
    # One batched query keyed by thread id avoids an N+1 over the 200 rows; a
    # row whose thread was since deleted simply gets no link (plain text).
    thread_ids = {r.ref_id for r in rows if r.ref_type == "thread" and r.ref_id}
    links: dict = {}
    if thread_ids:
        for tid, tname, pid, pname in db.execute(
            select(Thread.id, Thread.name, Project.id, Project.name)
            .join(Project, Project.id == Thread.project_id)
            .where(Thread.id.in_(thread_ids))
        ):
            links[tid] = {
                "project_id": str(pid),
                "thread_id": str(tid),
                "project_name": pname,
                "thread_name": tname,
            }

    return [
        {
            "id": r.id, "delta": r.delta, "reason": r.reason,
            "ref_type": r.ref_type, "ref_id": str(r.ref_id) if r.ref_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "link": links.get(r.ref_id) if r.ref_type == "thread" else None,
        }
        for r in rows
    ]

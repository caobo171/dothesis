"""PayPal payment integration (raw REST via httpx — no SDK).

Mirrors polar_client's dummy-mode escape hatch: when DOTHESIS_PAYMENTS=dummy or
no client id is configured, checkout/capture/verify return stub values so local
dev and tests run without real PayPal credentials.
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import httpx

from .settings import Settings, get_settings

if TYPE_CHECKING:
    from .models import Order

log = logging.getLogger(__name__)


class PayPalError(Exception):
    pass


def _is_dummy(settings: Settings | None = None) -> bool:
    """Dummy mode for OUTBOUND calls (create/capture order).

    Treating an absent client id as dummy is safe here — the worst case is a
    fake order id that moves no money. Never reuse it on a path that GRANTS
    something; see `_explicit_dummy`.
    """
    settings = settings or get_settings()
    return settings.dothesis_payments == "dummy" or not settings.paypal_client_id


def _explicit_dummy(settings: Settings | None = None) -> bool:
    """Dummy mode somebody ASKED for, rather than inferred from missing config.

    Mirrors polar_client._explicit_dummy, and exists for the same reason: the
    webhook below grants credit, and `_is_dummy` is true whenever PayPal is
    simply unconfigured. DoThesis ships `DOTHESIS_PAYMENTS=polar` with no PayPal
    credentials, so that route was live and skipping verification in production.

    The exploit needed no secret — start a real checkout to mint an Order row,
    then post PAYMENT.CAPTURE.COMPLETED with its id as `custom_id` instead of
    paying. Missing config now refuses; wanting the short circuit means saying
    `DOTHESIS_PAYMENTS=dummy`.
    """
    settings = settings or get_settings()
    return settings.dothesis_payments == "dummy"


def _base_url(settings: Settings) -> str:
    return (
        "https://api-m.paypal.com"
        if settings.paypal_mode == "production"
        else "https://api-m.sandbox.paypal.com"
    )


def _access_token(settings: Settings) -> str:
    resp = httpx.post(
        f"{_base_url(settings)}/v1/oauth2/token",
        auth=(settings.paypal_client_id, settings.paypal_secret),
        data={"grant_type": "client_credentials"},
        timeout=20.0,
    )
    if resp.status_code != 200:
        raise PayPalError(f"oauth failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()["access_token"]


def create_order(order: "Order", *, return_url: str, cancel_url: str) -> tuple[str, str]:
    """Create a PayPal order. Returns (paypal_order_id, approval_url)."""
    settings = get_settings()
    if _is_dummy(settings):
        oid = f"dummy_{uuid.uuid4().hex}"
        url = f"{settings.dothesis_base_url}/credit?paypal=dummy&order={order.id}"
        log.warning("paypal dummy mode — order %s gets fake order %s", order.id, oid)
        return oid, url

    token = _access_token(settings)
    usd = f"{order.amount_cents / 100:.2f}"
    resp = httpx.post(
        f"{_base_url(settings)}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {"currency_code": "USD", "value": usd},
                # Echoed back on capture + webhook so we can match the order.
                "custom_id": str(order.id),
            }],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": return_url,
                "cancel_url": cancel_url,
                "user_action": "PAY_NOW",
            }}},
        },
        timeout=30.0,
    )
    if resp.status_code not in (200, 201):
        raise PayPalError(f"create order failed: {resp.status_code} {resp.text[:200]}")
    body = resp.json()
    approve = next(
        (l["href"] for l in body.get("links", [])
         if l.get("rel") in ("payer-action", "approve")), None)
    if not approve:
        raise PayPalError("no approval link in PayPal response")
    return body["id"], approve


def capture_order(paypal_order_id: str) -> tuple[str, str | None]:
    """Capture an approved order. Returns (status, capture_id).

    status is the PayPal order status (COMPLETED on success); capture_id is the
    unique capture transaction id used as the grant idempotency key.
    """
    settings = get_settings()
    if _is_dummy(settings):
        return "COMPLETED", f"dummycap_{uuid.uuid4().hex}"

    token = _access_token(settings)
    resp = httpx.post(
        f"{_base_url(settings)}/v2/checkout/orders/{paypal_order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30.0,
    )
    if resp.status_code not in (200, 201):
        raise PayPalError(f"capture failed: {resp.status_code} {resp.text[:200]}")
    body = resp.json()
    capture_id = None
    try:
        capture_id = body["purchase_units"][0]["payments"]["captures"][0]["id"]
    except (KeyError, IndexError):
        pass
    return body.get("status", ""), capture_id


def verify_webhook(headers: dict, body: bytes) -> None:
    """Verify a PayPal webhook signature. Raises PayPalError on failure."""
    settings = get_settings()
    # `_explicit_dummy`, NOT `_is_dummy`: missing PayPal credentials must not
    # read as permission to skip verification on the path that grants credit.
    if _explicit_dummy(settings):
        return
    if not (settings.paypal_client_id and settings.paypal_webhook_id):
        # Half-configured is not configured — there is nothing to verify
        # against, and accepting on that basis is the same fail-open bug.
        raise PayPalError("paypal is not configured (client id / webhook id)")
    import json as _json

    token = _access_token(settings)
    resp = httpx.post(
        f"{_base_url(settings)}/v1/notifications/verify-webhook-signature",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": settings.paypal_webhook_id,
            "webhook_event": _json.loads(body),
        },
        timeout=20.0,
    )
    if resp.status_code != 200 or resp.json().get("verification_status") != "SUCCESS":
        raise PayPalError("webhook signature verification failed")

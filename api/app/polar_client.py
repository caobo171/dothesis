"""Polar payment integration. Falls back to dummy URLs when DOTHESIS_PAYMENTS=dummy."""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import TYPE_CHECKING

from .settings import Settings, get_settings

if TYPE_CHECKING:
    from .models import Order

log = logging.getLogger(__name__)


class PolarError(Exception):
    pass


def _is_dummy(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return settings.dothesis_payments == "dummy" or not settings.polar_access_token


def create_checkout(order: "Order", *, return_url: str, cancel_url: str) -> tuple[str, str]:
    """Create a Polar checkout. Returns (checkout_id, checkout_url)."""
    settings = get_settings()
    if _is_dummy(settings):
        cid = f"dummy_{uuid.uuid4().hex}"
        url = f"{settings.dothesis_base_url}/credit?polar=dummy&order={order.id}"
        log.warning("polar dummy mode — order %s gets fake checkout %s", order.id, cid)
        return cid, url

    from polar_sdk import Polar  # type: ignore
    client = Polar(access_token=settings.polar_access_token, server=settings.polar_server)
    resp = client.checkouts.create(request={
        "product_id": order.package_id,
        "success_url": return_url,
        "metadata": {"order_id": str(order.id), "user_id": str(order.user_id)},
    })
    return resp.id, resp.url


def verify_webhook(payload: bytes, signature: str) -> None:
    """Raise PolarError if the HMAC doesn't match."""
    settings = get_settings()
    if _is_dummy(settings):
        if not signature:
            raise PolarError("missing signature")
        return
    secret = settings.polar_webhook_secret.encode()
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PolarError("invalid signature")

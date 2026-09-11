"""Polar payment integration. Falls back to dummy URLs when DOTHESIS_PAYMENTS=dummy."""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from collections.abc import Mapping

from .settings import Settings, get_settings

if TYPE_CHECKING:
    from .models import Order

log = logging.getLogger(__name__)


class PolarError(Exception):
    pass


def _is_dummy(settings: Settings | None = None) -> bool:
    """Dummy mode for OUTBOUND calls (create_checkout).

    An absent access token counts here, and that is fine for a checkout: the
    worst case is a fake `?polar=dummy` URL that charges nobody. Do NOT reuse
    this for anything that GRANTS something — see `_explicit_dummy`.
    """
    settings = settings or get_settings()
    return settings.dothesis_payments == "dummy" or not settings.polar_access_token


def _explicit_dummy(settings: Settings | None = None) -> bool:
    """Dummy mode somebody ASKED for, rather than inferred from missing config.

    The distinction exists because inferring it on the INBOUND path was a hole:
    `_is_dummy` is true whenever the access token is absent, and the webhook
    skipped signature verification in dummy mode — so a production server
    deployed without `POLAR_ACCESS_TOKEN` granted credits to anyone who posted
    `{"type":"order.paid"}` at the endpoint. The endpoint is registered with
    Polar and publicly reachable, so obscurity was never protecting it.

    A missing env var is a broken deployment, and a broken deployment should
    stop selling rather than start giving the product away. Wanting the short
    circuit is a decision, so it has to be written down: `DOTHESIS_PAYMENTS=dummy`.
    """
    settings = settings or get_settings()
    return settings.dothesis_payments == "dummy"


def _product_id(package_id: str, settings: Settings) -> str:
    """Resolve a `pricing.PACKAGES` id to the Polar product UUID.

    These were conflated: the old code passed `order.package_id` straight through
    as Polar's `product_id`. Polar has never known what "starter_package" is — it
    keys on a UUID it minted when the product was created — so the call could only
    ever fail. It went unnoticed because production had no access token and sat in
    dummy mode, where this code path is never reached.

    Raises rather than returning None: an unmapped pack is an operator error
    (POLAR_PRODUCT_IDS missing an entry), and the alternative is sending a
    malformed request and reporting Polar's 422 as our 502.
    """
    mapping = dict(
        pair.split("=", 1)
        for pair in (p.strip() for p in settings.polar_product_ids.split(","))
        if pair and "=" in pair
    )
    product_id = mapping.get(package_id)
    if not product_id:
        raise PolarError(
            f"no Polar product mapped for package {package_id!r} — "
            f"add it to POLAR_PRODUCT_IDS"
        )
    return product_id


def create_checkout(order: "Order", *, return_url: str, cancel_url: str) -> tuple[str, str]:
    """Create a Polar checkout. Returns (checkout_id, checkout_url)."""
    settings = get_settings()
    if _is_dummy(settings):
        cid = f"dummy_{uuid.uuid4().hex}"
        url = f"{settings.dothesis_base_url}/credit?polar=dummy&order={order.id}"
        log.warning("polar dummy mode — order %s gets fake checkout %s", order.id, cid)
        return cid, url

    product_id = _product_id(order.package_id, settings)

    from polar_sdk import Polar  # type: ignore
    client = Polar(access_token=settings.polar_access_token, server=settings.polar_server)
    # `products`, plural, is the field the current API requires — a bare
    # `product_id` is dropped and the request 422s on "products: Field required".
    # One entry: a checkout offering a choice of packs would let the student pick
    # a pack other than the one the Order was priced and credited for.
    resp = client.checkouts.create(request={
        "products": [product_id],
        "success_url": return_url,
        "metadata": {"order_id": str(order.id), "user_id": str(order.user_id)},
    })
    return resp.id, resp.url


def verify_webhook(payload: bytes, headers: "Mapping[str, str]") -> None:
    """Raise PolarError unless `payload` carries a signature Polar could have made.

    Takes the whole header mapping, not one string, because Standard Webhooks
    signs `{webhook-id}.{webhook-timestamp}.{body}` — the signature cannot be
    checked without the other two headers.

    This previously computed a hex HMAC over the body alone and compared it to
    an `X-Polar-Signature` header. Polar sends none of that: the header is
    `webhook-signature`, the value is a space-separated list of `v1,<base64>`,
    and the id and timestamp are part of the signed string. Every real delivery
    would have failed, been retried, and eventually dropped — with the order
    paid and the credits never granted.

    Two key derivations are tried because Polar changed secret formats on
    2026-09-08: older secrets are used as raw bytes ("Polar HMAC"), newer ones
    are base64-decoded per Standard Webhooks. An account can hold endpoints from
    both eras at once, so accepting only one silently breaks the other. Polar's
    own SDKs ≥1.0.0-alpha.19 do the same thing; the pinned 0.31.5 implements
    only the old scheme, which is why this does not delegate to it.
    """
    settings = get_settings()
    hdrs = {k.lower(): v for k, v in headers.items()}
    # `x-polar-signature` stays accepted as a present-signature marker so the
    # dummy-mode tests and any legacy caller still get "missing" vs "invalid"
    # distinguished the same way.
    if not (hdrs.get("webhook-signature") or hdrs.get("x-polar-signature")):
        raise PolarError("missing signature")
    # `_explicit_dummy`, NOT `_is_dummy`: an absent access token must not be
    # read as permission to skip verification on the path that grants credit.
    if _explicit_dummy(settings):
        return

    from standardwebhooks.webhooks import Webhook  # noqa: PLC0415 — vendored via polar-sdk

    secret = settings.polar_webhook_secret
    if not secret:
        # Half-configured is not configured: there is nothing to verify against,
        # and accepting on that basis is the same fail-open bug one step along.
        raise PolarError("polar webhook secret is not configured")
    # str  -> strip `whsec_`, base64-decode  (Standard Webhooks, post 2026-09-08)
    # bytes-> use verbatim as the HMAC key    (Polar HMAC, pre 2026-09-08)
    for key in (secret, secret.encode()):
        try:
            Webhook(key).verify(payload, hdrs)
            return
        except Exception:  # noqa: BLE001, PERF203 — wrong era, try the other key
            continue
    raise PolarError("invalid signature")

"""Polar webhook signature verification.

Polar signs with Standard Webhooks: the signed string is
`{webhook-id}.{webhook-timestamp}.{body}`, the signature is base64, and it
arrives in a `webhook-signature` header as a space-separated list of
`v1,<sig>` entries.

The secret format changed under us. Polar's own docs:

    Secrets created after September 8, 2026 follow the "Standard Webhooks"
    specification. Older secrets use Polar HMAC instead.

The two differ only in how the secret becomes an HMAC key — raw bytes for the
old scheme, base64-decoded for the new one — so an endpoint created before that
date and one created after both have to verify here. Polar's own newer SDKs
resolve this by trying both keys; the pinned polar-sdk 0.31.5 only implements
the old one, which is why this does not just delegate to it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from math import floor
from types import SimpleNamespace

import pytest

from app.polar_client import PolarError, verify_webhook

SECRET = "polar_whs_hZ8kQ2vRtY6uW9xA3bC5dE7fG1hJ4kL0"
PAYLOAD = json.dumps({"type": "order.paid", "data": {"id": "ord_1"}}).encode()


@pytest.fixture(autouse=True)
def live_polar(monkeypatch):
    """A configured (non-dummy) Polar, so verification actually runs."""
    monkeypatch.setattr(
        "app.polar_client.get_settings",
        lambda: SimpleNamespace(dothesis_payments="polar",
                                polar_access_token="polar_oat_test",
                                polar_webhook_secret=SECRET),
    )


def _headers(key, payload: bytes = PAYLOAD, *, msg_id="msg_2vR", when=None) -> dict[str, str]:
    """Sign `payload` the way Polar does, with `key` as the HMAC key.

    `key` as str takes the standardwebhooks path (strip `whsec_`, base64-decode);
    as bytes it is used verbatim. That is precisely the two-scheme split above.
    """
    from standardwebhooks.webhooks import Webhook

    when = when or datetime.now(timezone.utc)
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": str(floor(when.timestamp())),
        "webhook-signature": Webhook(key).sign(msg_id, when, payload.decode()),
        "content-type": "application/json",
    }


def test_accepts_a_standard_webhooks_signature():
    """The post-2026-09-08 scheme: the secret is passed through as-is."""
    verify_webhook(PAYLOAD, _headers(SECRET))


def test_accepts_a_legacy_polar_hmac_signature():
    """The pre-2026-09-08 scheme: the secret's own bytes are the key.

    Endpoints created before the cutover still sign this way, and they did not
    get migrated — dropping this branch would silently break every existing
    Polar integration on the account.
    """
    verify_webhook(PAYLOAD, _headers(SECRET.encode()))


def test_rejects_a_tampered_body():
    """The signature covers the body; changing a credit amount must not verify."""
    headers = _headers(SECRET)
    tampered = PAYLOAD.replace(b"ord_1", b"ord_9")
    with pytest.raises(PolarError):
        verify_webhook(tampered, headers)


def test_rejects_a_signature_made_with_another_secret():
    with pytest.raises(PolarError):
        verify_webhook(PAYLOAD, _headers("polar_whs_completelyDifferentSecret00"))


def test_rejects_a_replayed_old_timestamp():
    """Standard Webhooks bounds timestamp skew — an intercepted delivery must
    not stay redeemable forever."""
    stale = datetime.now(timezone.utc) - timedelta(hours=6)
    with pytest.raises(PolarError):
        verify_webhook(PAYLOAD, _headers(SECRET, when=stale))


def test_rejects_when_the_signature_header_is_absent():
    with pytest.raises(PolarError):
        verify_webhook(PAYLOAD, {"content-type": "application/json"})

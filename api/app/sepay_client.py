"""SePay (VietQR bank-transfer) integration helpers.

SePay is merchant-side: there is no order-creation API call. We generate a
per-order VietQR image URL (qr.sepay.vn/img) with the package's VND amount and a
unique memo, then SePay's webhook tells us when a matching transfer arrives.
"""
from __future__ import annotations

from urllib.parse import urlencode

from .settings import Settings, get_settings


def is_enabled(settings: Settings | None = None) -> bool:
    """SePay is offered only when an account + bank code are configured."""
    settings = settings or get_settings()
    return bool(settings.sepay_account_number and settings.sepay_bank_code)


def usd_cents_to_vnd(amount_cents: int, settings: Settings | None = None) -> int:
    """Convert a USD-cents package price to a whole-VND amount at the fixed rate."""
    settings = settings or get_settings()
    return round(amount_cents / 100 * settings.usd_to_vnd)


def order_memo(order_id, settings: Settings | None = None) -> str:
    """Unique transfer memo for an order: PREFIX + the order's short hex.

    The hex (no dashes) keeps the memo within bank-transfer content limits and
    free of characters SePay strips. The webhook matches on the prefix + hex.
    """
    settings = settings or get_settings()
    short = str(order_id).replace("-", "")[:16]
    # Uppercased so it matches what memo_matches() extracts from webhook content
    # (banks/SePay often upper-case transfer memos anyway).
    return f"{settings.sepay_memo_prefix}{short}".upper()


def qr_image_url(memo: str, amount_vnd: int, settings: Settings | None = None) -> str:
    """Build the SePay VietQR image URL embedding the account, amount, and memo."""
    settings = settings or get_settings()
    qs = urlencode({
        "acc": settings.sepay_account_number,
        "bank": settings.sepay_bank_code,
        "amount": amount_vnd,
        "des": memo,
    })
    return f"https://qr.sepay.vn/img?{qs}"


def memo_matches(content: str, settings: Settings | None = None) -> str | None:
    """Extract our order memo from a SePay transfer's content, if present.

    SePay may wrap/prefix the memo, so we search for our prefix anywhere in the
    content and return the full `PREFIX+hex` token (uppercased, alnum only).
    Returns None when no memo of ours is found.
    """
    settings = settings or get_settings()
    if not content:
        return None
    cleaned = "".join(ch for ch in content.upper() if ch.isalnum())
    prefix = settings.sepay_memo_prefix.upper()
    idx = cleaned.find(prefix)
    if idx == -1:
        return None
    token = cleaned[idx:idx + len(prefix) + 16]
    return token or None

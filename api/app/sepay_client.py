"""SePay (VietQR bank-transfer) integration helpers.

SePay is merchant-side: there is no order-creation API call. We generate a
per-order VietQR image URL (qr.sepay.vn/img) with the package's VND amount and a
unique memo, then SePay's webhook tells us when a matching transfer arrives.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from .settings import Settings, get_settings

# SePay's VietinBank account is a *shared* collection account: many merchants
# receive into the same number, and SePay routes each transfer to the right one
# by a "SEVQR TKP " marker in front of the payment code. OCB numbers (SEPxxxx)
# are per-merchant virtual accounts, where the bare code is enough.
SHARED_CONTENT_PREFIX = "SEVQR TKP "
SHARED_ACCOUNT_BANKS = {"VIETINBANK", "VTB", "ICB", "CTG"}

# Upper bound on the digit run read back out of a transfer content. Codes are
# allocated from a sequence starting at 1000, so this is orders of magnitude of
# headroom while still capping what a malformed content can make us scan.
MAX_CODE_DIGITS = 12


def is_enabled(settings: Settings | None = None) -> bool:
    """SePay is offered only when an account + bank code are configured."""
    settings = settings or get_settings()
    return bool(settings.sepay_account_number and settings.sepay_bank_code)


def bank_display_name(settings: Settings | None = None) -> str:
    """Bank label for the pay modal — the configured name, else the code."""
    settings = settings or get_settings()
    return settings.sepay_bank_name or settings.sepay_bank_code


def usd_cents_to_vnd(amount_cents: int, settings: Settings | None = None) -> int:
    """Convert a USD-cents package price to a whole-VND amount at the fixed rate."""
    settings = settings or get_settings()
    return round(amount_cents / 100 * settings.usd_to_vnd)


def order_memo(code: int, settings: Settings | None = None) -> str:
    """Payment code for an order: PREFIX + a short serial ("DTS1234").

    Short and numeric on purpose. The code is retyped by hand into a banking
    app, has to survive bank content-length limits, and is what SePay's own
    code-detection config matches on — none of which the order UUID satisfies.
    Uniqueness comes from the caller's sequence, not from the value's width.
    """
    settings = settings or get_settings()
    return f"{settings.sepay_memo_prefix}{code}".upper()


def transfer_content(memo: str, settings: Settings | None = None) -> str:
    """What the payer must actually put in the transfer content.

    Identical to the memo on a virtual account; prefixed with "SEVQR TKP " on
    the shared VietinBank rail so SePay can route the money to us at all.
    """
    settings = settings or get_settings()
    if settings.sepay_bank_code.strip().upper() in SHARED_ACCOUNT_BANKS:
        return f"{SHARED_CONTENT_PREFIX}{memo}"
    return memo


def qr_image_url(content: str, amount_vnd: int, settings: Settings | None = None) -> str:
    """Build the SePay VietQR image URL embedding the account, amount, and content."""
    settings = settings or get_settings()
    qs = urlencode({
        "acc": settings.sepay_account_number,
        "bank": settings.sepay_bank_code,
        "amount": amount_vnd,
        "des": content,
    })
    return f"https://qr.sepay.vn/img?{qs}"


def memo_candidates(content: str, settings: Settings | None = None) -> list[str]:
    """Every memo a transfer's content could be carrying, longest first.

    Banks don't reliably delimit the content they echo back, and stripping
    punctuation collapses "DTS1234 20260810" into "DTS123420260810" — so a
    single greedy read of the digit run can swallow a trailing reference number
    and match nothing. Returning the progressively shorter readings lets the
    caller take the first one that names a real order. SePay's own `code` field,
    when configured, arrives clean and is simply the first candidate.

    Empty list when the content carries no memo of ours.
    """
    settings = settings or get_settings()
    if not content:
        return []
    cleaned = "".join(ch for ch in content.upper() if ch.isalnum())
    prefix = settings.sepay_memo_prefix.upper()
    m = re.search(rf"{re.escape(prefix)}(\d+)", cleaned)
    if not m:
        return []
    digits = m.group(1)[:MAX_CODE_DIGITS]
    return [f"{prefix}{digits[:n]}" for n in range(len(digits), 0, -1)]

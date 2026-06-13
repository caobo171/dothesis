"""Super-admin allowlist. Source of truth is this file; env var extends it."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User


_SEED: frozenset[str] = frozenset({
    "cao.nv17@gmail.com",
    "caotest171@gmail.com"
})


def _load_extra_emails() -> frozenset[str]:
    raw = os.environ.get("OPENDRAFT_SUPER_ADMIN_EMAILS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


SUPER_ADMIN_EMAILS: frozenset[str] = _SEED | _load_extra_emails()


def is_super_admin(user: "User") -> bool:
    """True iff the user's email (case-insensitive) is in the allowlist."""
    if not user or not getattr(user, "email", None):
        return False
    return user.email.lower() in SUPER_ADMIN_EMAILS

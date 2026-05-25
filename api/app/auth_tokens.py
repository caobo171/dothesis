"""itsdangerous-signed JWT-style tokens for email-bound links."""
from __future__ import annotations

import uuid

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .settings import get_settings

VERIFY_TTL = 24 * 3600   # 24 hours
RESET_TTL = 60 * 60      # 60 minutes


def _serializer() -> URLSafeTimedSerializer:
    s = get_settings()
    return URLSafeTimedSerializer(secret_key=s.session_secret, salt="auth-token")


def make_verify_token(user_id: uuid.UUID) -> str:
    return _serializer().dumps({"uid": str(user_id), "kind": "verify"})


def make_reset_token(user_id: uuid.UUID) -> str:
    return _serializer().dumps({"uid": str(user_id), "kind": "reset"})


def decode_token(token: str, *, kind: str, max_age: int) -> uuid.UUID:
    """Return the user_id, or raise ValueError on any failure."""
    try:
        data = _serializer().loads(token, max_age=max_age)
    except SignatureExpired:
        raise ValueError("token_expired")
    except BadSignature:
        raise ValueError("token_invalid")
    if not isinstance(data, dict) or data.get("kind") != kind:
        raise ValueError("token_mismatch")
    try:
        return uuid.UUID(data["uid"])
    except (KeyError, ValueError):
        raise ValueError("token_invalid")

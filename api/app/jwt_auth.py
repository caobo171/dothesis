"""Access-token auth machinery — replaces the cookie/session path.

Architecture: every authenticated POST body inherits from `AuthedBody`, which
declares `access_token: str`. The `current_user` dependency in `deps.py`
reads that field, calls `verify_access_token`, and returns the User row.
Stateless — no Session table lookup, no cookie machinery.

Why this exists:
- The old `opendraft_session` cookie path made cross-origin SSE fragile.
  Browsers refused to forward the cookie to localhost:7100 (Next.js dev was
  serving from localhost:3006) without `SameSite=None; Secure` — which
  doesn't work over http. Tokens in the request body sidestep all of that.
- The whole API is POST-only (CLAUDE.md). Every request has a body, so the
  token always has a place to ride.
- Matches the pattern in the user's other project (wele).

Token format:
- JWT (HS256), signed with `settings.session_secret` (renamed conceptually,
  same secret — same security domain).
- Claims: { sub: str(user_id), iat: int, exp: int }.
- 7-day expiry. No refresh flow yet — re-login when expired.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt as _jwt
from pydantic import BaseModel, Field

# 7 days. Generous enough that mobile sessions don't blow up; short enough
# that a leaked token can't be useful forever. Refresh flow is a deliberate
# follow-up — see CLAUDE.md / the migration plan.
ACCESS_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60

# Stream tokens ride in the URL of browser-GET-only endpoints (EventSource SSE
# + <a download>), which cannot carry a JSON body. Decision: keep them very
# short-lived (120s) and bound to ONE resource via `scope`, so a leaked URL is
# useful only for that resource for ~2 min and can NOT unlock the JSON API
# (verify_stream_token requires typ=="stream"). Not strictly single-use:
# EventSource reconnects reopen the same URL, so one-time use would break SSE.
STREAM_TOKEN_TTL_SECONDS = 120

# JWT algorithm: HS256 is symmetric (server signs + verifies with the same
# secret). Asymmetric (RS256) would let other services verify without the
# secret, but we have only one API process today; revisit when that changes.
_JWT_ALGO = "HS256"


@dataclass(slots=True)
class AccessTokenClaims:
    """Decoded token. `user_id` matches the User PK column."""
    user_id: str
    issued_at: int
    expires_at: int


def sign_access_token(user_id: str, *, secret: str,
                      ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS) -> tuple[str, int]:
    """Sign a JWT for `user_id`.

    Returns (token, expires_at_epoch). The expiry is returned alongside the
    token so the client can decide when to re-auth without re-parsing the
    JWT — avoids shipping a JWT-decoder to the browser.
    """
    now = int(time.time())
    exp = now + ttl_seconds
    payload: dict[str, Any] = {"sub": str(user_id), "iat": now, "exp": exp}
    token = _jwt.encode(payload, secret, algorithm=_JWT_ALGO)
    return token, exp


def verify_access_token(token: str, *, secret: str) -> AccessTokenClaims:
    """Verify and decode a JWT.

    Raises `ValueError` on bad signature / malformed / expired. Callers
    convert to HTTPException(401) — the dependency in deps.py does this.
    Never let a bare jwt exception bubble to the SSE stream; clients see
    the SSE error event and can't introspect a Python traceback.
    """
    try:
        payload = _jwt.decode(token, secret, algorithms=[_JWT_ALGO])
    except _jwt.ExpiredSignatureError as e:
        raise ValueError("token expired") from e
    except _jwt.InvalidTokenError as e:
        raise ValueError(f"bad token: {e}") from e
    # Reject stream tokens here: they are scoped, short-lived URL tokens and
    # must never unlock the full JSON API even if one leaks into a query string.
    # (Access tokens predate the `typ` claim, so we reject typ=="stream" rather
    # than requiring typ=="access", keeping already-issued tokens valid.)
    if payload.get("typ") == "stream":
        raise ValueError("not an access token")
    sub = payload.get("sub")
    iat = payload.get("iat")
    exp = payload.get("exp")
    if not isinstance(sub, str) or not isinstance(iat, int) or not isinstance(exp, int):
        raise ValueError("malformed token claims")
    return AccessTokenClaims(user_id=sub, issued_at=iat, expires_at=exp)


@dataclass(slots=True)
class StreamTokenClaims:
    user_id: str
    scope: str
    expires_at: int


def sign_stream_token(user_id: str, *, scope: str, secret: str,
                      ttl_seconds: int = STREAM_TOKEN_TTL_SECONDS) -> tuple[str, int]:
    """Sign a short-lived, resource-scoped token for a browser-GET endpoint.

    `scope` binds the token to one resource+action (e.g. "job:<id>",
    "paper-export:<id>:<fmt>", "project-export:<id>/<filename>"). Returns
    (token, expires_at_epoch).
    """
    now = int(time.time())
    exp = now + ttl_seconds
    payload: dict[str, Any] = {
        "sub": str(user_id), "scope": scope, "typ": "stream",
        "iat": now, "exp": exp,
    }
    return _jwt.encode(payload, secret, algorithm=_JWT_ALGO), exp


def verify_stream_token(token: str, *, expected_scope: str,
                        secret: str) -> StreamTokenClaims:
    """Verify a stream token AND that it was minted for `expected_scope`.

    Raises ValueError on bad signature / malformed / expired / wrong typ /
    scope mismatch. Scope is checked here (not just by the caller) so a token
    minted for resource A can never be replayed against resource B.
    """
    try:
        payload = _jwt.decode(token, secret, algorithms=[_JWT_ALGO])
    except _jwt.ExpiredSignatureError as e:
        raise ValueError("stream token expired") from e
    except _jwt.InvalidTokenError as e:
        raise ValueError(f"bad stream token: {e}") from e
    if payload.get("typ") != "stream":
        raise ValueError("not a stream token")
    sub = payload.get("sub")
    scope = payload.get("scope")
    exp = payload.get("exp")
    if not isinstance(sub, str) or not isinstance(scope, str) or not isinstance(exp, int):
        raise ValueError("malformed stream token claims")
    if scope != expected_scope:
        raise ValueError(f"stream token scope mismatch: {scope!r} != {expected_scope!r}")
    return StreamTokenClaims(user_id=sub, scope=scope, expires_at=exp)


class AuthedBody(BaseModel):
    """Base class for every authenticated request body.

    Every POST endpoint that requires a logged-in user MUST have its body
    schema inherit from this — that guarantees the access_token field is
    validated by FastAPI before the endpoint runs, and gives the
    `current_user` dependency something concrete to read.

    Endpoints that take no other parameters still inherit this and accept
    `{"access_token": "..."}` — no separate "tokenless" body shape.

    The field is named `access_token` (not `token` or `auth`) to match the
    convention in the user's other project (wele), keeping the wire format
    learnable across projects.
    """
    access_token: str = Field(
        ...,
        description="JWT issued by /auth/login or /auth/signup. 7-day expiry.",
        min_length=1,
    )

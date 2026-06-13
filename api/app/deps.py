"""Auth dependencies — reads access_token from request body.

History: this file used to read `opendraft_session` cookie and look up a row
in the Session table. That path is gone — see jwt_auth.py for the why.

The `current_user` dependency below works for any POST endpoint whose body
inherits from `AuthedBody` (or any body that happens to carry an
`access_token` field). It does NOT consume the body in a way that prevents
the endpoint from parsing its own typed body: Starlette caches the raw
request bytes after the first `.body()` call, so both the dependency and
the endpoint see the same JSON.
"""
from __future__ import annotations

import json
from typing import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import db_session
from .jwt_auth import verify_access_token, verify_stream_token
from .models import User
from .settings import Settings, get_settings


def _401(code: str, message: str) -> HTTPException:
    """Uniform 401 shape so the frontend's error handler can branch on
    `code` (e.g., `expired` → re-auth flow, `bad_token` → wipe localStorage).
    Matches the shape the old cookie path used so existing client code
    paths continue to parse the body the same way."""
    return HTTPException(
        status_code=401,
        detail={"error": {"code": code, "message": message}},
    )


async def _extract_token(request: Request) -> str | None:
    """Find an access_token in the request, trying transports in order.

    Order of preference:
      1. `access_token` field inside the JSON body (POST endpoints — the
         canonical path per CLAUDE.md).
      2. `?access_token=...` query parameter (transitional path for the
         GETs we haven't migrated to POST yet — see CLAUDE.md "migrate
         when next edited" rule).
      3. `Authorization: Bearer <token>` header (for curl / Postman /
         non-browser tooling; the web client never uses this path).

    Returns the first token found or None. Callers raise 401 on None.

    Body-mode failures are silent here so query/header fallbacks still run.
    """
    # Body — only for requests that actually carry one.
    try:
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
                if isinstance(body, dict):
                    t = body.get("access_token")
                    if isinstance(t, str) and t:
                        return t
            except json.JSONDecodeError:
                pass  # bad JSON falls through to query / header
    except Exception:  # noqa: BLE001
        pass

    # Query string — keeps existing GET endpoints working until they're
    # migrated to POST per CLAUDE.md. New code should NOT rely on this.
    t = request.query_params.get("access_token")
    if isinstance(t, str) and t:
        return t

    # Authorization header — tooling-only path. Same secret; same token.
    auth = request.headers.get("authorization")
    if isinstance(auth, str) and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None


async def current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(db_session),
) -> User:
    """Resolve the User row from an access_token.

    Token comes from the request body (POST endpoints) OR the query string
    (legacy GETs during migration) OR an Authorization Bearer header
    (tooling). Body wins when multiple are present.

    Raises 401 with a structured `code` for: missing token, bad/expired
    token, user not found.
    """
    token = await _extract_token(request)
    if not token:
        raise _401("no_token", "missing access_token (body / query / Bearer)")

    try:
        claims = verify_access_token(token, secret=settings.session_secret)
    except ValueError as e:
        # ValueError from jwt_auth covers expired AND malformed; surface the
        # message so the client can distinguish via the detail string
        # without re-implementing JWT parsing.
        code = "expired" if "expired" in str(e) else "bad_token"
        raise _401(code, str(e))

    try:
        user_uuid = claims.user_id  # str(uuid)
        user = db.get(User, user_uuid)
    except Exception:  # noqa: BLE001 — bad UUID format etc.
        raise _401("bad_token", "token claims malformed")

    if user is None:
        # Token was valid at signing time but user was deleted. Treat as
        # auth failure so the client wipes its token; a 404 here would
        # leak account-existence semantics.
        raise _401("no_user", "user not found")
    return user


def stream_user_factory(scope_builder: Callable[..., str]):
    """Build a dependency for browser-GET-only endpoints (SSE / downloads).

    The endpoint can't carry a JSON body, so auth rides in `?st=<stream_token>`.
    `scope_builder(**path_params)` returns the scope the token MUST match —
    binding the token to exactly the resource in the URL. We still return the
    User so the endpoint's existing ownership checks (_owned_project etc.) run
    as a second gate (defense in depth).
    """
    async def _dep(
        request: Request,
        settings: Settings = Depends(get_settings),
        db: Session = Depends(db_session),
    ) -> User:
        token = request.query_params.get("st")
        if not token:
            raise _401("no_token", "missing stream token (?st=)")
        expected_scope = scope_builder(**request.path_params)
        try:
            claims = verify_stream_token(
                token, expected_scope=expected_scope, secret=settings.session_secret)
        except ValueError as e:
            code = "expired" if "expired" in str(e) else "bad_token"
            raise _401(code, str(e))
        user = db.get(User, claims.user_id)
        if user is None:
            raise _401("no_user", "user not found")
        return user
    return _dep

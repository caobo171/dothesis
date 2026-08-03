"""OAuth 2.1 façade for the DoThesis MCP server — MCP_OAUTH_PLAN.md item 2.

WHAT THIS IS FOR
----------------
Claude's remote-connector flow will not talk to an MCP server that has no
authorization server. Pointing it at a bare endpoint makes it fetch the
discovery documents, find nothing, fall back to treating the origin as its own
authorization server, POST dynamic client registration, get HTML back, and
report "Couldn't register with <site>'s sign-in service". That message is the
registration step failing — not a network or TLS problem. This module is the
authorization server that makes the message go away.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not add an identity provider. DoThesis already knows who the user is:
`web/app/lib/tokenStore.ts` mirrors the access-token JWT into a non-HTTPOnly
`dothesis_access_token` cookie (SameSite=Lax, path=/) so the Next middleware can
gate routes server-side. Because MCP is path-routed onto the SAME origin as the
web app, that cookie is sent to `/oauth/authorize` on top-level navigation —
which is exactly the navigation Claude performs. So "log the user in" here means
"read the session the browser already has", and only when there isn't one do we
bounce to /login. No second login, no new vendor, no Google round-trip of our
own. This is the whole reason path-routing (commit 67ae7d7) was worth keeping.

WHY IT RE-IMPLEMENTS JWT VERIFY INSTEAD OF IMPORTING api/app/jwt_auth.py
------------------------------------------------------------------------
`mcp/README.md` states the architecture rule: the MCP server never imports
DoThesis in-process, it calls the API over HTTP, so the two dependency trees
never meet. Importing `app.jwt_auth` would drag in `app.settings`, pydantic-
settings and the DB layer for the sake of eight lines of PyJWT. The cost of the
duplication is a coupling that must be kept in sync BY HAND: same secret
(`SESSION_SECRET`), same algorithm (HS256), same `sub` claim. If jwt_auth.py's
format changes, this file changes with it. That is written down in README.md.

TOKENS WE ISSUE
---------------
The access token we hand Claude is a DoThesis access-token JWT: HS256 over
`SESSION_SECRET`, `sub` = the user id, plus `typ: "mcp"` and the client id. That
is a deliberate choice, not an accident of convenience — `api/app/deps.py`
already accepts `Authorization: Bearer <token>` and `verify_access_token`
already admits any token that isn't `typ="stream"`. So the MCP server can simply
FORWARD the caller's bearer to `/api/v1/humanize` and the request runs as that
user, with that user's credits and quotas, through the same code path the web
app uses. Nothing about metering, ownership or auth has to be re-implemented.

The honest consequence, stated plainly because it is a real one: an MCP access
token is a full-power DoThesis token for that account, not a humanize-only
capability. It is scoped down by TIME instead (1 hour, vs 7 days for a web
session) and backed by a rotating, revocable refresh token. Narrowing it further
means teaching `verify_access_token` about `typ="mcp"` — a change to the API's
auth core, which is a bigger blast radius than this connector deserves today.

STORAGE
-------
DoThesis's own Postgres, reached with plain psycopg and hand-written SQL. The
tables (`mcp_oauth_clients`, `mcp_oauth_codes`, `mcp_oauth_refresh_tokens`) are
declared once in `api/app/models.py` and created by alembic like everything
else.

This module still imports nothing from `app.*` — the boundary that matters is
"no shared Python objects", and that is intact. But the DATA is not private to
this process, so keeping it in a process-local SQLite file cost real things:
connector installs are a campaign metric that should be a query; a "Disconnect"
button in DoThesis's UI needs the API to see these grants; and a foreign key to
`users` means deleting an account takes its grants with it. One database, one
backup, one place to look.

⚠️ The SQL below is hand-written against `models.py`. Change a column there and
change it here. That is the deliberate cost of staying import-free.

Secrets are stored as SHA-256 digests; they are 256-bit random strings, so a
password KDF would buy nothing.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import os
import secrets
import time
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, urlunparse

import jwt as _jwt
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

# --- Tunables ---------------------------------------------------------------

# Auth codes are exchanged by the client within a second or two of being issued;
# 60s is generous. Short TTL is the main defence for a credential that travels
# in a URL and therefore lands in browser history and proxy logs.
AUTH_CODE_TTL_SECONDS = 60

# 1 hour. See the module docstring: this token carries full account authority,
# so its TTL is the primary containment. Claude refreshes silently.
ACCESS_TOKEN_TTL_SECONDS = 60 * 60

# 30 days, rotated on every use. Rotation means a stolen refresh token stops
# working as soon as the legitimate client refreshes once (and vice versa) —
# the theft becomes visible instead of silent.
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60

SCOPE = "dothesis:mcp"
JWT_ALGO = "HS256"  # must match api/app/jwt_auth.py

SESSION_COOKIE = "dothesis_access_token"  # written by web/app/lib/tokenStore.ts


def _secret() -> str:
    s = os.getenv("SESSION_SECRET", "")
    if not s:
        raise RuntimeError(
            "SESSION_SECRET is not set. The MCP OAuth façade signs tokens with the "
            "same secret as the DoThesis API — without it, nothing it issues would "
            "be accepted by /api/v1/*.")
    return s


# --- Storage ----------------------------------------------------------------

def _dsn() -> str:
    """libpq connection string, read per call so tests can rebind DATABASE_URL.

    DoThesis stores the URL in SQLAlchemy form (`postgresql+psycopg://…`); the
    `+driver` suffix is SQLAlchemy's own notation and libpq rejects it, so it
    comes off here.
    """
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. The MCP OAuth façade stores registered "
            "clients and refresh tokens in DoThesis's Postgres.")
    return url.replace("postgresql+psycopg://", "postgresql://", 1) \
              .replace("postgresql+psycopg2://", "postgresql://", 1)


@contextlib.contextmanager
def _db():
    """A connection that commits on clean exit, rolls back on error, and closes.

    One connection per request rather than a pool: this process handles a
    handful of OAuth calls per connector setup and then nothing for hours, so a
    pool would mostly be idle sockets. If the connector ever gets chatty,
    psycopg_pool is the drop-in.
    """
    conn = psycopg.connect(_dsn(), row_factory=dict_row, connect_timeout=10)
    try:
        with conn:          # commits, or rolls back if the body raises
            yield conn
    finally:
        conn.close()


def _sweep(conn) -> None:
    """Drop expired rows. Opportunistic (called on writes) rather than a timer:
    the tables are small and a background task would be one more thing to
    supervise in a process that is deliberately a single uvicorn worker."""
    now = _now()
    conn.execute("DELETE FROM mcp_oauth_codes WHERE expires_at < %s", (now,))
    conn.execute("DELETE FROM mcp_oauth_refresh_tokens WHERE expires_at < %s", (now,))


def _now() -> datetime:
    """Timestamps are `timestamptz` now, not unix ints — Postgres compares them
    correctly across DST and the API can read them without conversion."""
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --- Helpers ----------------------------------------------------------------

def _base_url(request) -> str:
    """The public origin this server is reachable at.

    Derived from the request (honouring the proxy's X-Forwarded-Proto) rather
    than configured, for the reason given in commit 67ae7d7: a second copy of
    the origin is a second thing to set per environment and a second thing to
    get wrong. `DOTHESIS_MCP_PUBLIC_URL` overrides it for the case where the
    proxy cannot be trusted to set the headers.
    """
    override = os.getenv("DOTHESIS_MCP_PUBLIC_URL", "").rstrip("/")
    if override:
        return override
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


# Public alias: server_lite.py needs this to build the WWW-Authenticate hint, and
# that hint must point at the same origin the discovery documents advertise.
base_url = _base_url


def _oauth_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=status)


def _redirect_with(redirect_uri: str, params: dict) -> RedirectResponse:
    """Append params to the client's redirect_uri, preserving any it already has."""
    parts = urlparse(redirect_uri)
    query = parts.query + "&" + urlencode(params) if parts.query else urlencode(params)
    return RedirectResponse(urlunparse(parts._replace(query=query)), status_code=302)


def _session_user(request) -> str | None:
    """The DoThesis user id from the browser session cookie, or None.

    The cookie value is the access-token JWT itself, URL-encoded by
    tokenStore.ts (base64url segments can contain characters Cookie syntax
    forbids). Starlette has already percent-decoded it by the time we read it.

    An expired or forged cookie returns None, which sends the user to /login —
    the same outcome as no cookie at all, and never an error page.
    """
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        claims = _jwt.decode(raw, _secret(), algorithms=[JWT_ALGO])
    except _jwt.InvalidTokenError:
        return None
    # Stream tokens are scoped, 2-minute URL tokens (api/app/jwt_auth.py); they
    # must not be promoted into a long-lived MCP grant.
    if claims.get("typ") == "stream":
        return None
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        return None
    # `user_id` is now a real FK to users.id, so a `sub` that isn't a UUID would
    # blow up the INSERT with a Postgres cast error instead of a clean redirect
    # to /login. Signature-valid tokens always carry one; this catches the
    # hand-rolled token someone signs while debugging.
    try:
        _uuid.UUID(sub)
    except ValueError:
        return None
    return sub


def mint_access_token(user_id: str, client_id: str) -> tuple[str, int]:
    """Sign a DoThesis access token for `user_id`, tagged as MCP-issued.

    Claim shape mirrors api/app/jwt_auth.sign_access_token (sub/iat/exp) so the
    API accepts it unchanged, plus `typ`/`client_id` for log forensics — when a
    token shows up in an audit, we want to know it came from a connector and
    which one.
    """
    now = int(time.time())
    exp = now + ACCESS_TOKEN_TTL_SECONDS
    token = _jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": exp,
         "typ": "mcp", "client_id": client_id, "scope": SCOPE},
        _secret(), algorithm=JWT_ALGO)
    return token, exp


def verify_bearer(token: str) -> str | None:
    """Return the user id for a bearer token issued here, else None."""
    return bearer_identity(token)[0]


def bearer_identity(token: str) -> tuple[str | None, str | None]:
    """(user_id, client_id) for a bearer token, or (None, None) if it's no good.

    The client id rides in the token because the audit log wants to say WHICH
    connector made a call, not just which user — a student with both Claude and
    ChatGPT connected is otherwise indistinguishable from one hammering a single
    client. It is absent on tokens minted before this claim existed, and on the
    dev static-token path, so callers must tolerate None.
    """
    try:
        claims = _jwt.decode(token, _secret(), algorithms=[JWT_ALGO])
    except _jwt.InvalidTokenError:
        return None, None
    if claims.get("typ") == "stream":
        return None, None
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        return None, None
    # Same UUID guard as _session_user. Everything downstream treats `sub` as a
    # users.id: the audit INSERT casts it to uuid, and the API looks it up. A
    # signed token with a malformed sub can only have come from us, so this is
    # a consistency check rather than a security boundary — but letting one
    # through trades a clean 401 for a failed audit write and a confusing error
    # from the API instead.
    try:
        _uuid.UUID(sub)
    except ValueError:
        return None, None
    cid = claims.get("client_id")
    return sub, cid if isinstance(cid, str) and cid else None


# --- Discovery --------------------------------------------------------------

def protected_resource_metadata(request):
    """RFC 9728. This is the document Claude fetches FIRST, and the one whose
    absence produced the registration error: with no `authorization_servers`
    pointer, the client has to guess, and guessing lands on the web app."""
    base = _base_url(request)
    return JSONResponse({
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [SCOPE],
        "resource_documentation": f"{base}/connect",
    })


def authorization_server_metadata(request):
    """RFC 8414. Note every endpoint lives under /oauth/ rather than at the
    origin root (/authorize, /token, /register). The root paths belong to the
    Next.js app — squatting on them is how the guide page ended up shadowing
    the MCP endpoint in commit a0c01d3. Clients follow these URLs, so the
    prefix costs nothing and keeps one nginx location responsible for us."""
    base = _base_url(request)
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": [
            "none", "client_secret_post", "client_secret_basic"],
        # S256 only. OAuth 2.1 removes "plain", and accepting it would let a
        # client that can intercept the redirect replay the code.
        "code_challenge_methods_supported": ["S256"],
    })


# --- Dynamic client registration (RFC 7591) ---------------------------------

async def register(request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _oauth_error("invalid_client_metadata", "body must be JSON")
    if not isinstance(body, dict):
        return _oauth_error("invalid_client_metadata", "body must be a JSON object")

    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris or not all(isinstance(u, str) and u for u in uris):
        return _oauth_error("invalid_redirect_uri", "redirect_uris must be a non-empty array of strings")
    for u in uris:
        p = urlparse(u)
        # Loopback http is allowed for desktop clients that listen on 127.0.0.1;
        # everything else must be https, or the code is exposed in transit.
        if p.scheme == "https":
            continue
        if p.scheme == "http" and p.hostname in ("127.0.0.1", "::1", "localhost"):
            continue
        return _oauth_error("invalid_redirect_uri", f"redirect_uri must be https (or loopback http): {u}")

    auth_method = body.get("token_endpoint_auth_method") or "none"
    if auth_method not in ("none", "client_secret_post", "client_secret_basic"):
        return _oauth_error("invalid_client_metadata",
                            f"unsupported token_endpoint_auth_method: {auth_method}")

    client_id = f"dt_{secrets.token_urlsafe(24)}"
    client_secret = None if auth_method == "none" else secrets.token_urlsafe(32)
    name = str(body.get("client_name") or "Unnamed MCP client")[:120]
    now = int(time.time())

    with _db() as conn:
        _sweep(conn)
        conn.execute(
            "INSERT INTO mcp_oauth_clients (client_id, secret_hash, client_name, "
            "redirect_uris, auth_method) VALUES (%s,%s,%s,%s,%s)",
            (client_id, _hash(client_secret) if client_secret else None,
             name, Jsonb(uris), auth_method))

    out = {
        "client_id": client_id,
        "client_id_issued_at": now,
        "client_name": name,
        "redirect_uris": uris,
        "token_endpoint_auth_method": auth_method,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    if client_secret:
        out["client_secret"] = client_secret
        out["client_secret_expires_at"] = 0  # 0 = never, per RFC 7591
    return JSONResponse(out, status_code=201)


# --- Authorization ----------------------------------------------------------

_CONSENT_PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect {client} to DoThesis</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         display: flex; min-height: 100vh; margin: 0; align-items: center;
         justify-content: center; background: #f6f7f9; color: #1a1d21; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #16181c; color: #e8eaed; }} }}
  .card {{ background: canvas; max-width: 27rem; width: calc(100% - 2rem); padding: 2rem;
          border-radius: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.12), 0 8px 32px rgba(0,0,0,.08); }}
  h1 {{ font-size: 1.15rem; margin: 0 0 .35rem; }}
  p  {{ margin: .35rem 0 0; color: #5b6470; }}
  @media (prefers-color-scheme: dark) {{ p {{ color: #a4adb8; }} }}
  ul {{ margin: 1.1rem 0 0; padding-left: 1.1rem; }}
  li {{ margin: .3rem 0; }}
  .row {{ display: flex; gap: .6rem; margin-top: 1.6rem; }}
  button {{ flex: 1; padding: .7rem 1rem; border-radius: 10px; font-size: .95rem;
           font-weight: 600; cursor: pointer; border: 1px solid transparent; }}
  .allow {{ background: #2563eb; color: #fff; }}
  .deny  {{ background: transparent; border-color: #c9cfd6; color: inherit; }}
  code {{ font-size: .85em; word-break: break-all; }}
</style>
<div class="card">
  <h1>Connect {client} to DoThesis</h1>
  <p>Signed in as <strong>{user}</strong>.</p>
  <ul>
    <li>Rewrite text you send it with the <strong>humanize</strong> tool</li>
    <li>Spend credits from this DoThesis account</li>
  </ul>
  <p>Redirects to <code>{redirect}</code>.</p>
  <form method="post" action="/oauth/authorize">
    {fields}
    <div class="row">
      <button class="deny" name="approve" value="0" type="submit">Cancel</button>
      <button class="allow" name="approve" value="1" type="submit">Allow</button>
    </div>
  </form>
</div>
"""


def _validated_request(params, conn):
    """Shared validation for GET (render consent) and POST (act on it).

    Returns (client_row, error_response). Errors that we cannot safely bounce
    back to the client — unknown client, unregistered redirect_uri — are
    rendered here instead, because redirecting them would turn this endpoint
    into an open redirector.
    """
    client_id = params.get("client_id") or ""
    redirect_uri = params.get("redirect_uri") or ""
    row = conn.execute("SELECT * FROM mcp_oauth_clients WHERE client_id = %s",
                       (client_id,)).fetchone()
    if row is None:
        return None, _oauth_error("invalid_client", "unknown client_id")
    # JSONB comes back already decoded, unlike the TEXT column this replaced.
    if redirect_uri not in row["redirect_uris"]:
        return None, _oauth_error("invalid_request", "redirect_uri does not match a registered URI")
    return row, None


def authorize(request):
    params = request.query_params
    with _db() as conn:
        row, err = _validated_request(params, conn)
    if err:
        return err

    redirect_uri = params["redirect_uri"]
    state = params.get("state", "")

    if params.get("response_type") != "code":
        return _redirect_with(redirect_uri, {
            "error": "unsupported_response_type", "state": state})
    challenge = params.get("code_challenge", "")
    if not challenge or params.get("code_challenge_method") != "S256":
        return _redirect_with(redirect_uri, {
            "error": "invalid_request",
            "error_description": "PKCE with code_challenge_method=S256 is required",
            "state": state})

    user_id = _session_user(request)
    if not user_id:
        # No DoThesis session in this browser. Send them through the normal web
        # login and come straight back — `next` is a same-origin absolute path,
        # which is all web/app/login/page.jsx will accept.
        nxt = f"/oauth/authorize?{urlencode(dict(params))}"
        return RedirectResponse(f"/login?next={_quote(nxt)}", status_code=302)

    fields = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in params.items())
    return HTMLResponse(_CONSENT_PAGE.format(
        client=html.escape(row["client_name"]),
        user=html.escape(_user_label(request, user_id)),
        redirect=html.escape(redirect_uri),
        fields=fields))


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def _user_label(request, user_id: str) -> str:
    """Best-effort display name for the consent screen.

    We only have the JWT, which carries `sub` and nothing else — resolving an
    email would mean a DB round-trip this process deliberately doesn't have. The
    truncated id is enough for the one thing the screen must answer: "is this
    the account I think it is?" for a user with more than one.
    """
    return f"DoThesis account …{user_id[-6:]}"


async def authorize_decision(request):
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    with _db() as conn:
        row, err = _validated_request(params, conn)
        if err:
            return err

        redirect_uri = params["redirect_uri"]
        state = params.get("state", "")

        if params.get("approve") != "1":
            return _redirect_with(redirect_uri, {"error": "access_denied", "state": state})

        # Re-read the cookie rather than trusting anything the form carried: the
        # form is attacker-shapeable, the cookie is not. Cross-site POSTs don't
        # carry it at all (SameSite=Lax), which is what stops a hostile page
        # from silently minting a code for its own client.
        user_id = _session_user(request)
        if not user_id:
            return _redirect_with(redirect_uri, {
                "error": "access_denied",
                "error_description": "session expired during consent",
                "state": state})

        challenge = params.get("code_challenge", "")
        if not challenge or params.get("code_challenge_method") != "S256":
            return _redirect_with(redirect_uri, {"error": "invalid_request", "state": state})

        code = secrets.token_urlsafe(32)
        _sweep(conn)
        conn.execute(
            "INSERT INTO mcp_oauth_codes (code_hash, client_id, user_id, redirect_uri, "
            "code_challenge, scope, resource, expires_at, used) "
            "VALUES (%s,%s,%s::uuid,%s,%s,%s,%s,%s,false)",
            (_hash(code), row["client_id"], user_id, redirect_uri, challenge, SCOPE,
             params.get("resource"),
             _now() + timedelta(seconds=AUTH_CODE_TTL_SECONDS)))

    out = {"code": code}
    if state:
        out["state"] = state
    return _redirect_with(redirect_uri, out)


# --- Token ------------------------------------------------------------------

def _authenticate_client(request, form, conn):
    """Resolve + authenticate the client on a token request.

    Public clients (auth_method "none") are identified by client_id alone —
    that is what PKCE exists to make safe. Confidential clients must present
    their secret, by Basic header or form field.
    """
    client_id = form.get("client_id")
    secret = form.get("client_secret")

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth.split(" ", 1)[1]).decode()
            basic_id, _, basic_secret = decoded.partition(":")
            client_id = client_id or basic_id
            secret = secret or basic_secret
        except Exception:  # noqa: BLE001
            return None, _oauth_error("invalid_client", "malformed Basic credentials", 401)

    if not client_id:
        return None, _oauth_error("invalid_client", "client_id is required", 401)
    row = conn.execute("SELECT * FROM mcp_oauth_clients WHERE client_id = %s",
                       (client_id,)).fetchone()
    if row is None:
        return None, _oauth_error("invalid_client", "unknown client_id", 401)
    if row["secret_hash"]:
        if not secret or not secrets.compare_digest(_hash(secret), row["secret_hash"]):
            return None, _oauth_error("invalid_client", "bad client_secret", 401)
    return row, None


def _pkce_ok(verifier: str, challenge: str) -> bool:
    if not verifier:
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return secrets.compare_digest(expected, challenge)


async def token(request):
    form = {k: str(v) for k, v in (await request.form()).items()}
    grant = form.get("grant_type")

    with _db() as conn:
        row, err = _authenticate_client(request, form, conn)
        if err:
            return err
        _sweep(conn)

        if grant == "authorization_code":
            code = form.get("code") or ""
            code_hash = _hash(code)
            rec = conn.execute("SELECT * FROM mcp_oauth_codes WHERE code_hash = %s",
                               (code_hash,)).fetchone()
            if rec is None or rec["expires_at"] < _now():
                return _oauth_error("invalid_grant", "authorization code is invalid or expired")
            if rec["used"]:
                # Replay. The legitimate exchange already happened, so the code
                # is in someone else's hands — kill the whole grant rather than
                # just refusing this call.
                conn.execute("DELETE FROM mcp_oauth_codes WHERE code_hash = %s",
                             (code_hash,))
                conn.execute("UPDATE mcp_oauth_refresh_tokens SET revoked = true "
                             "WHERE client_id = %s AND user_id = %s",
                             (rec["client_id"], rec["user_id"]))
                return _oauth_error("invalid_grant", "authorization code already used")
            if rec["client_id"] != row["client_id"]:
                return _oauth_error("invalid_grant", "code was issued to a different client")
            if form.get("redirect_uri", "") != rec["redirect_uri"]:
                return _oauth_error("invalid_grant", "redirect_uri does not match the request")
            if not _pkce_ok(form.get("code_verifier", ""), rec["code_challenge"]):
                return _oauth_error("invalid_grant", "PKCE verification failed")

            conn.execute("UPDATE mcp_oauth_codes SET used = true WHERE code_hash = %s",
                         (code_hash,))
            return _issue(conn, row["client_id"], rec["user_id"])

        if grant == "refresh_token":
            presented = form.get("refresh_token") or ""
            rec = conn.execute("SELECT * FROM mcp_oauth_refresh_tokens "
                               "WHERE token_hash = %s",
                               (_hash(presented),)).fetchone()
            if rec is None or rec["revoked"] or rec["expires_at"] < _now():
                return _oauth_error("invalid_grant", "refresh token is invalid, expired or revoked")
            if rec["client_id"] != row["client_id"]:
                return _oauth_error("invalid_grant", "refresh token belongs to a different client")
            # Rotate: this one dies as the replacement is minted.
            conn.execute("UPDATE mcp_oauth_refresh_tokens SET revoked = true "
                         "WHERE token_hash = %s", (_hash(presented),))
            return _issue(conn, row["client_id"], rec["user_id"])

    return _oauth_error("unsupported_grant_type", f"unsupported grant_type: {grant}")


def _issue(conn, client_id: str, user_id: str) -> JSONResponse:
    access, exp = mint_access_token(user_id, client_id)
    refresh = secrets.token_urlsafe(48)
    conn.execute(
        "INSERT INTO mcp_oauth_refresh_tokens (token_hash, client_id, user_id, scope, "
        "expires_at, revoked) VALUES (%s,%s,%s::uuid,%s,%s,false)",
        (_hash(refresh), client_id, str(user_id), SCOPE,
         _now() + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)))
    return JSONResponse({
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": exp - int(time.time()),
        "refresh_token": refresh,
        "scope": SCOPE,
    }, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


async def revoke(request):
    """RFC 7009. Always answers 200 — telling a caller whether an unknown token
    existed is itself a disclosure, and the RFC requires success regardless."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    with _db() as conn:
        _, err = _authenticate_client(request, form, conn)
        if err:
            return err
        presented = form.get("token") or ""
        conn.execute("UPDATE mcp_oauth_refresh_tokens SET revoked = true "
                     "WHERE token_hash = %s", (_hash(presented),))
    return Response(status_code=200)


# --- Route table ------------------------------------------------------------

def routes() -> list[Route]:
    """Mounted by server_lite.py alongside /mcp.

    The `.well-known` documents are served at BOTH the bare path and the
    path-aware `/mcp` suffix (RFC 9728 §3.1). Which one a client asks for
    depends on its spec revision, the cost of answering both is one route, and
    guessing wrong reproduces the exact bug this module exists to fix.
    """
    return [
        Route("/.well-known/oauth-protected-resource", protected_resource_metadata),
        Route("/.well-known/oauth-protected-resource/mcp", protected_resource_metadata),
        Route("/.well-known/oauth-authorization-server", authorization_server_metadata),
        Route("/.well-known/oauth-authorization-server/mcp", authorization_server_metadata),
        Route("/oauth/register", register, methods=["POST"]),
        Route("/oauth/authorize", authorize, methods=["GET"]),
        Route("/oauth/authorize", authorize_decision, methods=["POST"]),
        Route("/oauth/token", token, methods=["POST"]),
        Route("/oauth/revoke", revoke, methods=["POST"]),
    ]

"""OAuth 2.1 façade for the MCP connector — mcp/oauth.py + mcp/server_lite.py.

These tests exist because the failure they guard against is invisible from the
inside. A broken discovery document or a mis-derived issuer URL doesn't raise;
it produces a working-looking server that Claude refuses with "Couldn't register
with dothesis's sign-in service" and no further detail. So the assertions here
are mostly about the SHAPE of what we publish and the exact bytes a client will
follow, not just about happy-path plumbing.

No network and no DoThesis API call: the façade is pure token machinery, and the
one place it would call out (`tools/call` → /api/v1/humanize) is not exercised
here. It DOES need Postgres — grants live in DoThesis's database now, with a
foreign key to `users` — which is why this file sits in api/tests/ next to the
testcontainers fixture rather than in the root suite.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import os
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from tests.conftest import make_user

MCP_DIR = Path(__file__).resolve().parents[2] / "mcp"
SECRET = "test-session-secret-for-mcp-oauth"


@pytest.fixture()
def user_id(pg_url):
    """A real users row — `user_id` is a foreign key now, not a free-text field."""
    with Session(get_engine()) as s:
        u = make_user(s)
        s.commit()
        return str(u.id)


@pytest.fixture()
def mcp(monkeypatch, pg_url):
    """Import mcp/oauth.py + server_lite.py bound to the test database.

    `DATABASE_URL` is read per connection rather than at import, so pointing it
    at the testcontainer here is enough. `REQUIRE_AUTH` IS read at import, hence
    the re-import per test — fine for a single-purpose daemon, and cheaper than
    adding indirection to production code for the sake of tests.
    """
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DOTHESIS_MCP_REQUIRE_AUTH", "1")
    monkeypatch.delenv("DOTHESIS_MCP_PUBLIC_URL", raising=False)
    monkeypatch.syspath_prepend(str(MCP_DIR))
    for name in ("oauth", "server_lite"):
        sys.modules.pop(name, None)
    oauth = importlib.import_module("oauth")
    server_lite = importlib.import_module("server_lite")
    yield oauth, server_lite
    for name in ("oauth", "server_lite"):
        sys.modules.pop(name, None)


@pytest.fixture()
def client(mcp):
    from starlette.testclient import TestClient
    _, server_lite = mcp
    # base_url + headers stand in for nginx: the façade derives every URL it
    # publishes from these, so getting them wrong here would mask exactly the
    # bug this file is about.
    with TestClient(server_lite.app, base_url="https://app.dothesis.com") as c:
        c.headers.update({"X-Forwarded-Proto": "https", "Host": "app.dothesis.com"})
        yield c


def _session_cookie(user_id: str, *, typ: str | None = None) -> str:
    """A DoThesis access-token JWT, as web/app/lib/tokenStore.ts would store it."""
    import jwt

    now = int(time.time())
    claims = {"sub": user_id, "iat": now, "exp": now + 3600}
    if typ:
        claims["typ"] = typ
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    return verifier, challenge


def _register(client, redirect_uri="https://claude.ai/api/mcp/auth_callback"):
    r = client.post("/oauth/register",
                    json={"client_name": "Claude", "redirect_uris": [redirect_uri]})
    assert r.status_code == 201, r.text
    return r.json()


# --- Discovery --------------------------------------------------------------

def test_protected_resource_metadata_points_at_our_own_origin(client):
    r = client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    body = r.json()
    # The whole point of this document: tell the client that the resource at
    # /mcp is guarded by an authorization server, and which one.
    assert body["resource"] == "https://app.dothesis.com/mcp"
    assert body["authorization_servers"] == ["https://app.dothesis.com"]


def test_discovery_is_served_at_both_the_bare_and_path_aware_locations(client):
    """Which one a client requests depends on its spec revision. Answering only
    one reproduces the original bug for half of them."""
    for path in ("/.well-known/oauth-protected-resource",
                 "/.well-known/oauth-protected-resource/mcp",
                 "/.well-known/oauth-authorization-server",
                 "/.well-known/oauth-authorization-server/mcp"):
        assert client.get(path).status_code == 200, path


def test_as_metadata_advertises_the_oauth_prefixed_endpoints(client):
    body = client.get("/.well-known/oauth-authorization-server").json()
    assert body["issuer"] == "https://app.dothesis.com"
    assert body["registration_endpoint"] == "https://app.dothesis.com/oauth/register"
    assert body["authorization_endpoint"] == "https://app.dothesis.com/oauth/authorize"
    assert body["token_endpoint"] == "https://app.dothesis.com/oauth/token"
    # OAuth 2.1 drops "plain"; advertising it would invite a downgrade.
    assert body["code_challenge_methods_supported"] == ["S256"]


def test_issuer_follows_the_forwarded_proto_not_the_internal_scheme(mcp):
    """nginx terminates TLS and talks plain HTTP to :9000. If the façade trusted
    the connection scheme it would publish http:// URLs, and every client would
    refuse them (or worse, follow them)."""
    from starlette.testclient import TestClient
    _, server_lite = mcp
    with TestClient(server_lite.app, base_url="http://127.0.0.1:9000") as c:
        body = c.get("/.well-known/oauth-authorization-server",
                     headers={"X-Forwarded-Proto": "https",
                              "Host": "app.dothesis.com"}).json()
    assert body["issuer"] == "https://app.dothesis.com"


# --- Dynamic client registration -------------------------------------------

def test_registration_issues_a_public_client_by_default(client):
    body = _register(client)
    assert body["client_id"].startswith("dt_")
    assert body["token_endpoint_auth_method"] == "none"
    # A public client must not be handed a secret it cannot keep.
    assert "client_secret" not in body


def test_registration_issues_a_secret_for_confidential_clients(client):
    r = client.post("/oauth/register", json={
        "client_name": "Server-side", "redirect_uris": ["https://example.com/cb"],
        "token_endpoint_auth_method": "client_secret_post"})
    assert r.status_code == 201
    assert r.json()["client_secret"]


@pytest.mark.parametrize("uri", [
    "http://evil.example/cb",      # plaintext, non-loopback → code stealable in transit
    "ftp://example.com/cb",
])
def test_registration_rejects_unsafe_redirect_uris(client, uri):
    r = client.post("/oauth/register",
                    json={"client_name": "x", "redirect_uris": [uri]})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"


def test_registration_allows_loopback_http_for_desktop_clients(client):
    r = client.post("/oauth/register", json={
        "client_name": "Desktop", "redirect_uris": ["http://127.0.0.1:33418/cb"]})
    assert r.status_code == 201


# --- Authorization ----------------------------------------------------------

def test_authorize_without_a_session_bounces_through_the_web_login(client):
    reg = _register(client)
    _, challenge = _pkce()
    r = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": reg["redirect_uris"][0], "state": "xyz",
        "code_challenge": challenge, "code_challenge_method": "S256",
    }, follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("/login?next=")
    # The round-trip target must come back to us with the query intact,
    # otherwise the user logs in and the handshake is simply lost.
    nxt = parse_qs(urlparse(loc).query)["next"][0]
    assert nxt.startswith("/oauth/authorize?")
    assert "code_challenge" in nxt


def test_authorize_with_a_session_renders_consent(client, user_id):
    reg = _register(client)
    _, challenge = _pkce()
    client.cookies.set("dothesis_access_token", _session_cookie(user_id))
    r = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": reg["redirect_uris"][0],
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    assert r.status_code == 200
    assert "Connect Claude to DoThesis" in r.text
    # The user must be able to see WHERE the grant is going before allowing it.
    assert "claude.ai/api/mcp/auth_callback" in r.text


def test_authorize_refuses_an_unregistered_redirect_uri_without_redirecting(client, user_id):
    """The anti-open-redirect case. Bouncing this error back to the supplied URI
    would make the endpoint a redirector for any URL an attacker chooses."""
    reg = _register(client)
    _, challenge = _pkce()
    client.cookies.set("dothesis_access_token", _session_cookie(user_id))
    r = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": "https://evil.example/steal",
        "code_challenge": challenge, "code_challenge_method": "S256",
    }, follow_redirects=False)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


def test_authorize_requires_pkce(client, user_id):
    reg = _register(client)
    client.cookies.set("dothesis_access_token", _session_cookie(user_id))
    r = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": reg["redirect_uris"][0], "state": "s1",
    }, follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["error"] == ["invalid_request"]
    assert q["state"] == ["s1"]


def test_a_stream_token_cookie_is_not_a_session(client, user_id):
    """Stream tokens are 2-minute, resource-scoped URL tokens (jwt_auth.py). One
    leaking into the cookie jar must not be upgradeable into a 30-day grant."""
    reg = _register(client)
    _, challenge = _pkce()
    client.cookies.set("dothesis_access_token", _session_cookie(user_id, typ="stream"))
    r = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": reg["redirect_uris"][0],
        "code_challenge": challenge, "code_challenge_method": "S256",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/login?next=")


# --- Full handshake ---------------------------------------------------------

def _consent_to_code(client, reg, challenge, user_id, state="st-1"):
    client.cookies.set("dothesis_access_token", _session_cookie(user_id))
    r = client.post("/oauth/authorize", data={
        "approve": "1", "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": reg["redirect_uris"][0], "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }, follow_redirects=False)
    assert r.status_code == 302, r.text
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["state"] == [state]
    return q["code"][0]


def test_authorization_code_exchange_yields_a_usable_dothesis_token(client, mcp, user_id):
    oauth, _ = mcp
    reg = _register(client)
    verifier, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)

    r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": reg["redirect_uris"][0],
        "client_id": reg["client_id"], "code_verifier": verifier})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["refresh_token"]
    # Tokens must never be cached by an intermediary.
    assert "no-store" in r.headers.get("cache-control", "")

    # The issued token is a DoThesis access token for the consenting user —
    # that is what lets the MCP server forward it to /api/v1/humanize unchanged.
    import jwt
    claims = jwt.decode(body["access_token"], SECRET, algorithms=["HS256"])
    assert claims["sub"] == user_id
    assert claims["typ"] == "mcp"
    assert claims["client_id"] == reg["client_id"]
    assert oauth.verify_bearer(body["access_token"]) == user_id


def test_denying_consent_returns_access_denied_and_mints_nothing(client, user_id):
    reg = _register(client)
    _, challenge = _pkce()
    client.cookies.set("dothesis_access_token", _session_cookie(user_id))
    r = client.post("/oauth/authorize", data={
        "approve": "0", "response_type": "code", "client_id": reg["client_id"],
        "redirect_uri": reg["redirect_uris"][0], "state": "s",
        "code_challenge": challenge, "code_challenge_method": "S256",
    }, follow_redirects=False)
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["error"] == ["access_denied"]
    assert "code" not in q


def test_pkce_verifier_mismatch_is_rejected(client, user_id):
    reg = _register(client)
    _, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)
    r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": reg["redirect_uris"][0],
        "client_id": reg["client_id"], "code_verifier": "not-the-verifier"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_redirect_uri_must_match_the_one_the_code_was_issued_for(client, user_id):
    reg = _register(client, redirect_uri="https://claude.ai/api/mcp/auth_callback")
    verifier, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)
    r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": "https://claude.ai/other", "client_id": reg["client_id"],
        "code_verifier": verifier})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_replaying_a_code_kills_the_whole_grant(client, user_id):
    """A second use means the code leaked. Refusing just the replay would leave
    the tokens from the FIRST (possibly attacker) exchange alive."""
    reg = _register(client)
    verifier, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)
    payload = {"grant_type": "authorization_code", "code": code,
               "redirect_uri": reg["redirect_uris"][0],
               "client_id": reg["client_id"], "code_verifier": verifier}
    first = client.post("/oauth/token", data=payload)
    assert first.status_code == 200
    refresh = first.json()["refresh_token"]

    replay = client.post("/oauth/token", data=payload)
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"

    # ...and the refresh token handed out on the first exchange is now dead.
    after = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": refresh,
        "client_id": reg["client_id"]})
    assert after.status_code == 400


def test_refresh_rotates_and_retires_the_old_token(client, user_id):
    reg = _register(client)
    verifier, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)
    first = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": reg["redirect_uris"][0],
        "client_id": reg["client_id"], "code_verifier": verifier}).json()

    second = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": first["refresh_token"],
        "client_id": reg["client_id"]})
    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]

    reused = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": first["refresh_token"],
        "client_id": reg["client_id"]})
    assert reused.status_code == 400


def test_a_code_cannot_be_redeemed_by_a_different_client(client, user_id):
    victim = _register(client)
    attacker = _register(client, redirect_uri="https://attacker.example/cb")
    verifier, challenge = _pkce()
    code = _consent_to_code(client, victim, challenge, user_id)
    r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": victim["redirect_uris"][0],
        "client_id": attacker["client_id"], "code_verifier": verifier})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_revoke_kills_a_refresh_token(client, user_id):
    reg = _register(client)
    verifier, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)
    issued = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": reg["redirect_uris"][0],
        "client_id": reg["client_id"], "code_verifier": verifier}).json()

    assert client.post("/oauth/revoke", data={
        "token": issued["refresh_token"], "client_id": reg["client_id"]}).status_code == 200
    assert client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": issued["refresh_token"],
        "client_id": reg["client_id"]}).status_code == 400


# --- The MCP endpoint itself ------------------------------------------------

def test_unauthenticated_mcp_call_points_the_client_at_discovery(client):
    """The load-bearing 401. Without the resource_metadata hint a client has to
    guess where to authenticate, and guessing is what produced the original
    "Couldn't register with dothesis's sign-in service"."""
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 401
    www = r.headers["www-authenticate"]
    assert www.startswith("Bearer ")
    assert ('resource_metadata="https://app.dothesis.com'
            '/.well-known/oauth-protected-resource/mcp"') in www


def test_garbage_bearer_is_rejected(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_an_expired_token_is_rejected(client):
    import jwt
    stale = jwt.encode({"sub": "u1", "iat": 0, "exp": int(time.time()) - 10},
                       SECRET, algorithm="HS256")
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={"Authorization": f"Bearer {stale}"})
    assert r.status_code == 401


def test_an_issued_token_unlocks_tools_list(client, user_id):
    reg = _register(client)
    verifier, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)
    access = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": reg["redirect_uris"][0],
        "client_id": reg["client_id"], "code_verifier": verifier}).json()["access_token"]

    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    # The full registry (mcp/tools.py); humanize is the one this file cares about.
    assert "humanize" in [t["name"] for t in r.json()["result"]["tools"]]


def test_registered_clients_survive_a_process_restart(mcp, user_id):
    """A restart that silently de-registers Claude reproduces the original error
    message with no clue as to why — so the store has to be durable and shared,
    not process memory."""
    from starlette.testclient import TestClient
    oauth, server_lite = mcp
    with TestClient(server_lite.app, base_url="https://app.dothesis.com") as c:
        reg = _register(c)

    importlib.reload(oauth)
    with TestClient(server_lite.app, base_url="https://app.dothesis.com") as c:
        c.cookies.set("dothesis_access_token", _session_cookie(user_id))
        _, challenge = _pkce()
        r = c.get("/oauth/authorize", params={
            "response_type": "code", "client_id": reg["client_id"],
            "redirect_uri": reg["redirect_uris"][0],
            "code_challenge": challenge, "code_challenge_method": "S256",
        }, headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200


# --- audit trail ------------------------------------------------------------

def _authed(client, user_id):
    """Complete the handshake and return the bearer, as a real client would."""
    reg = _register(client)
    verifier, challenge = _pkce()
    code = _consent_to_code(client, reg, challenge, user_id)
    tok = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": reg["redirect_uris"][0],
        "client_id": reg["client_id"], "code_verifier": verifier}).json()
    return tok["access_token"], reg["client_id"]


def _calls(pg_url, user_id):
    import psycopg
    from psycopg.rows import dict_row
    dsn = pg_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        return c.execute("SELECT * FROM mcp_tool_calls WHERE user_id = %s::uuid "
                         "ORDER BY id", (user_id,)).fetchall()


def test_a_tool_call_is_recorded_with_user_and_client(client, user_id, pg_url, monkeypatch):
    """The whole point: attribute a call to a person and a connector. The MCP
    access log says only 'POST /mcp 200'."""
    import server_lite

    async def _fake(tool, args, token):
        return {"ok": True, "text": "re-voiced output", "changed": True}
    monkeypatch.setattr(server_lite, "_call_tool", _fake)

    access, client_id = _authed(client, user_id)
    r = client.post("/mcp", headers={"Authorization": f"Bearer {access}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "humanize",
                                     "arguments": {"text": "some input prose"}}})
    assert r.status_code == 200

    rows = _calls(pg_url, user_id)
    assert len(rows) == 1
    assert rows[0]["tool"] == "humanize"
    assert rows[0]["ok"] is True
    assert rows[0]["client_id"] == client_id
    assert rows[0]["input_chars"] == len("some input prose")
    assert rows[0]["output_chars"] == len("re-voiced output")


def test_a_tool_refusal_is_recorded_as_a_failure(client, user_id, pg_url, monkeypatch):
    """ok=false inside a 200 is the tool declining (no_anchor). It is the case an
    admin most often has to explain to a student, so it must not read as success."""
    import server_lite

    async def _fake(tool, args, token):
        return {"ok": False, "error": "no_anchor", "text": args["text"]}
    monkeypatch.setattr(server_lite, "_call_tool", _fake)

    access, _ = _authed(client, user_id)
    client.post("/mcp", headers={"Authorization": f"Bearer {access}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "humanize", "arguments": {"text": "x"}}})

    rows = _calls(pg_url, user_id)
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["error"] == "no_anchor"


def test_an_upstream_crash_is_still_recorded(client, user_id, pg_url, monkeypatch):
    """A connector that throws for one user is exactly what the log exists to
    surface; a success-only record would hide it."""
    import server_lite

    async def _boom(tool, args, token):
        raise RuntimeError("upstream exploded")
    monkeypatch.setattr(server_lite, "_call_tool", _boom)

    access, _ = _authed(client, user_id)
    r = client.post("/mcp", headers={"Authorization": f"Bearer {access}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "humanize", "arguments": {"text": "x"}}})
    assert r.json()["result"]["isError"] is True

    rows = _calls(pg_url, user_id)
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert "upstream exploded" in rows[0]["error"]


def test_auditing_never_breaks_the_tool_call(client, user_id, monkeypatch):
    """The tool result is the product; the audit row is bookkeeping. Bookkeeping
    does not get to veto the product."""
    import audit
    import server_lite

    async def _fake(tool, args, token):
        return {"ok": True, "text": "fine", "changed": True}
    monkeypatch.setattr(server_lite, "_call_tool", _fake)

    def _explode(**kw):
        raise RuntimeError("database on fire")
    monkeypatch.setattr(audit, "record", _explode)

    access, _ = _authed(client, user_id)
    r = client.post("/mcp", headers={"Authorization": f"Bearer {access}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "humanize", "arguments": {"text": "x"}}})
    assert r.status_code == 200
    assert r.json()["result"]["structuredContent"]["text"] == "fine"


def test_no_prose_reaches_the_audit_table(client, user_id, pg_url, monkeypatch):
    """Sizes, never content. Thesis drafts are the most private thing here."""
    import server_lite
    secret_text = "MY UNPUBLISHED THESIS PARAGRAPH"

    async def _fake(tool, args, token):
        return {"ok": True, "text": "rewritten " + secret_text}
    monkeypatch.setattr(server_lite, "_call_tool", _fake)

    access, _ = _authed(client, user_id)
    client.post("/mcp", headers={"Authorization": f"Bearer {access}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "humanize", "arguments": {"text": secret_text}}})

    row = _calls(pg_url, user_id)[0]
    assert secret_text not in " ".join(str(v) for v in row.values())
    assert row["input_chars"] == len(secret_text)

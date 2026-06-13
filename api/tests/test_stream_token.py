import time
import pytest
from app.jwt_auth import sign_stream_token, verify_stream_token

SECRET = "x" * 32

def test_roundtrip_ok():
    tok, exp = sign_stream_token("user-1", scope="job:abc", secret=SECRET)
    claims = verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)
    assert claims.user_id == "user-1"
    assert claims.scope == "job:abc"
    assert exp > int(time.time())

def test_wrong_scope_rejected():
    tok, _ = sign_stream_token("user-1", scope="job:abc", secret=SECRET)
    with pytest.raises(ValueError, match="scope"):
        verify_stream_token(tok, expected_scope="job:other", secret=SECRET)

def test_expired_rejected():
    tok, _ = sign_stream_token("u", scope="job:abc", secret=SECRET, ttl_seconds=-1)
    with pytest.raises(ValueError, match="expired"):
        verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)

def test_access_token_not_accepted_as_stream():
    # An ordinary access token (no typ=stream) must not pass stream verification.
    from app.jwt_auth import sign_access_token
    tok, _ = sign_access_token("u", secret=SECRET)
    with pytest.raises(ValueError):
        verify_stream_token(tok, expected_scope="job:abc", secret=SECRET)

def test_stream_token_rejected_by_access_verify():
    # A stream token must NEVER pass as a full access token, else a leaked
    # stream URL could be replayed against the whole JSON API.
    from app.jwt_auth import sign_stream_token, verify_access_token
    tok, _ = sign_stream_token("u", scope="job:abc", secret=SECRET)
    with pytest.raises(ValueError):
        verify_access_token(tok, secret=SECRET)

def test_legacy_access_token_without_typ_still_valid():
    # Existing access tokens carry no `typ` claim; they must keep working.
    from app.jwt_auth import sign_access_token, verify_access_token
    tok, _ = sign_access_token("u", secret=SECRET)
    claims = verify_access_token(tok, secret=SECRET)
    assert claims.user_id == "u"

def test_stream_wrong_secret_rejected():
    tok, _ = sign_stream_token("u", scope="job:abc", secret=SECRET)
    with pytest.raises(ValueError):
        verify_stream_token(tok, expected_scope="job:abc", secret="y" * 32)

def test_stream_garbage_token_rejected():
    with pytest.raises(ValueError):
        verify_stream_token("not.a.jwt", expected_scope="job:abc", secret=SECRET)

def test_stream_user_dependency():
    # stream_user_factory builds a FastAPI dependency that reads ?st=, verifies
    # scope (computed from the request path params), and returns the User.
    from app.deps import stream_user_factory
    assert callable(stream_user_factory(lambda **kw: f"job:{kw['job_id']}"))


def test_stream_user_missing_token_raises_401():
    # The inner dependency must reject a request with no ?st= as a clean 401.
    # asyncio.run variant — no pytest-asyncio plugin dependency needed.
    import asyncio
    from fastapi import HTTPException
    from app.deps import stream_user_factory
    dep = stream_user_factory(lambda **kw: "job:abc")
    class _Req:
        query_params = {}
        path_params = {}
    with pytest.raises(HTTPException) as ei:
        # _dep checks ?st= FIRST and raises before touching settings/db, so
        # passing None for both is safe for the missing-token path.
        asyncio.run(dep(_Req(), settings=None, db=None))
    assert ei.value.status_code == 401


# --- Task 3: POST /auth/stream-token mint endpoint ---------------------------
# These exercise the HTTP route (not just the jwt helpers above). We seed a
# verified user and mint a real access token via `create_session`, which signs
# with `get_settings().session_secret` — the SAME secret the route uses and the
# SAME secret we hand to verify_stream_token below, so the round-trip is honest.

def _signed_in():
    """Build a TestClient + a valid access token for a freshly seeded user.

    Mirrors test_jobs._signed_in_client but returns the raw token too, because
    this route needs the access_token in the POST BODY (POST-only, per
    CLAUDE.md) rather than only an Authorization header.
    """
    from fastapi.testclient import TestClient
    from app.db import get_session_factory
    from app.main import create_app
    from app.models import User
    from app.security import create_session, hash_password
    Session = get_session_factory()
    with Session() as db:
        u = User(email="streamer@x.com", username="streamer",
                 password_hash=hash_password("supersecret"),
                 email_verified=True, credit=0)
        db.add(u)
        db.commit()
        token = create_session(db, u)
    return TestClient(create_app()), token


def test_mint_stream_token_endpoint():
    from app.jwt_auth import verify_stream_token
    from app.settings import get_settings
    client, auth_token = _signed_in()
    r = client.post("/api/v1/auth/stream-token",
                    json={"access_token": auth_token, "scope": "job:abc"})
    assert r.status_code == 200, r.text
    st = r.json()["stream_token"]
    claims = verify_stream_token(st, expected_scope="job:abc",
                                 secret=get_settings().session_secret)
    assert claims.scope == "job:abc"


def test_mint_requires_valid_access_token():
    client, _ = _signed_in()
    r = client.post("/api/v1/auth/stream-token",
                    json={"access_token": "garbage", "scope": "job:abc"})
    assert r.status_code == 401

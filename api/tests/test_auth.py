from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session_factory
from app.main import create_app
from app.models import User


def _client():
    return TestClient(create_app())


def _mark_verified(email: str) -> None:
    """Skip the email-link round-trip — flip email_verified in-DB so the
    test can call /login directly. The verify endpoint is exercised in
    test_auth_signup_verify.py."""
    Session = get_session_factory()
    with Session() as db:
        u = db.scalar(select(User).where(User.email == email))
        assert u is not None
        u.email_verified = True
        db.commit()


def test_signup_login_me_logout_flow():
    c = _client()

    # Signup: creates the user but does NOT auth — must verify email first.
    r = c.post("/api/v1/auth/signup",
               json={"username": "alice1", "email": "a@b.com", "password": "supersecret"})
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "a@b.com"
    # The new contract: no token, no cookie. Just an ok/email envelope.
    assert "access_token" not in r.json()

    # Skip the email-link path; flip the verified flag and log in.
    _mark_verified("a@b.com")
    r = c.post("/api/v1/auth/login",
               json={"email": "a@b.com", "password": "supersecret"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["user"]["email"] == "a@b.com"
    token = payload["access_token"]
    assert token and isinstance(token, str)
    assert isinstance(payload["expires_at"], int)

    # /me: POST with token in body. The new current_user dependency reads
    # access_token from body OR query string OR Authorization header — use
    # the body path here (canonical per CLAUDE.md).
    r = c.post("/api/v1/auth/me", json={"access_token": token})
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.com"

    # Logout is a stateless no-op (204). Client wipes its localStorage on
    # its end — there's no server state to clean.
    r = c.post("/api/v1/auth/logout")
    assert r.status_code == 204

    # /me without token → 401 (no_token).
    r = c.post("/api/v1/auth/me", json={})
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["error"]["code"] in {"no_token", "no_body"}

    # /me with a clearly-bad token → 401 (bad_token).
    r = c.post("/api/v1/auth/me", json={"access_token": "not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "bad_token"


def test_signup_duplicate_returns_409():
    c = _client()
    c.post("/api/v1/auth/signup",
           json={"username": "bob1", "email": "x@y.com", "password": "supersecret"})
    r = c.post("/api/v1/auth/signup",
               json={"username": "bob2", "email": "x@y.com", "password": "supersecret"})
    assert r.status_code == 409


def test_login_wrong_password_returns_401():
    c = _client()
    c.post("/api/v1/auth/signup",
           json={"username": "carol1", "email": "a@b.com", "password": "supersecret"})
    _mark_verified("a@b.com")
    r = c.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "nope1234"})
    assert r.status_code == 401

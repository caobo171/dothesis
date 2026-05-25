from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def _seed_user(email, *, password="supersecret", verified=False, google_id=None):
    Session = get_session_factory()
    with Session() as s:
        u = User(
            email=email, username=email.split("@")[0],
            password_hash=hash_password(password),
            email_verified=verified,
            google_id=google_id,
        )
        s.add(u)
        s.commit()
        return u


def test_login_unverified_returns_403_with_code():
    _seed_user("alice@e.com", verified=False)
    c = _client()
    r = c.post("/api/v1/auth/login", json={"email": "alice@e.com", "password": "supersecret"})
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["error"]["code"] == "unverified"
    assert body["detail"]["error"]["email"] == "alice@e.com"


def test_login_verified_succeeds():
    _seed_user("bob@e.com", verified=True)
    c = _client()
    r = c.post("/api/v1/auth/login", json={"email": "bob@e.com", "password": "supersecret"})
    assert r.status_code == 200
    assert "opendraft_session" in c.cookies


def test_login_google_account_bad_password_returns_use_google():
    _seed_user("g@e.com", password="random-throwaway", verified=True, google_id="abc123")
    c = _client()
    r = c.post("/api/v1/auth/login", json={"email": "g@e.com", "password": "wrong-guess"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "use_google"


def test_login_sets_last_login():
    _seed_user("ll@e.com", verified=True)
    c = _client()
    c.post("/api/v1/auth/login", json={"email": "ll@e.com", "password": "supersecret"})

    Session = get_session_factory()
    with Session() as s:
        from sqlalchemy import select
        u = s.scalar(select(User).where(User.email == "ll@e.com"))
        assert u.last_login is not None

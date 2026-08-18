from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import hash_password
from app.settings import reset_settings


def _client():
    return TestClient(create_app())


def _seed_user(email, *, password="supersecret", verified=False, google_id=None):
    # password=None seeds an account with NO password (empty hash) — how
    # Google-created accounts are stored. Anything else is hashed normally.
    Session = get_session_factory()
    with Session() as s:
        u = User(
            email=email, username=email.split("@")[0],
            password_hash=hash_password(password) if password is not None else "",
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
    # Was: cookie was set. New contract: TokenOut payload in the body.
    payload = r.json()
    assert isinstance(payload.get("access_token"), str) and payload["access_token"]
    assert isinstance(payload.get("expires_at"), int)


def test_login_google_account_bad_password_returns_use_google():
    # A Google-only account stores an empty hash. (This used to seed a hash of
    # a "random-throwaway" string, mirroring the old fabricated-hash scheme —
    # which is precisely what made a Google-only account indistinguishable
    # from a password account that had merely been mistyped.)
    _seed_user("g@e.com", password=None, verified=True, google_id="abc123")
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


def test_local_test_password_bypasses_password_hash(monkeypatch):
    _seed_user("support-login@e.com", password="unknown-real-password", verified=True)
    monkeypatch.setenv("TEST_PASSWORD", "Cao12345678")
    monkeypatch.setenv("WEB_ORIGIN", "http://localhost:3006")
    reset_settings()
    try:
        r = _client().post("/api/v1/auth/login", json={
            "email": "support-login@e.com", "password": "Cao12345678"})
        assert r.status_code == 200
    finally:
        reset_settings()


def test_test_password_is_ignored_on_production_origin(monkeypatch):
    _seed_user("production-login@e.com", password="real-password", verified=True)
    monkeypatch.setenv("TEST_PASSWORD", "Cao12345678")
    monkeypatch.setenv("WEB_ORIGIN", "https://dothesis.example")
    monkeypatch.setenv("DOTHESIS_TEST_SUPPORT", "0")
    reset_settings()
    try:
        r = _client().post("/api/v1/auth/login", json={
            "email": "production-login@e.com", "password": "Cao12345678"})
        assert r.status_code == 401
        assert r.json()["detail"]["error"]["code"] == "bad_credentials"
    finally:
        reset_settings()

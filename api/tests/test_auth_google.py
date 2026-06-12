from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def test_google_first_signin_creates_user_with_bonus(monkeypatch):
    monkeypatch.setenv("OPENDRAFT_SIGNUP_BONUS_CREDITS", "100")
    monkeypatch.setenv("OPENDRAFT_GOOGLE_CLIENT_ID", "test-id")
    from app import settings as sm; sm._settings = None

    fake_info = {"email": "new@gmail.com", "google_id": "g_99", "name": "New User"}
    with patch("app.routers.auth.verify_google_id_token", return_value=fake_info):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "FAKE"})
    assert r.status_code == 200, r.text
    # New contract: TokenOut in the body (no cookie).
    payload = r.json()
    assert isinstance(payload.get("access_token"), str) and payload["access_token"]
    assert isinstance(payload.get("expires_at"), int)

    Session = get_session_factory()
    with Session() as s:
        from sqlalchemy import select
        u = s.scalar(select(User).where(User.email == "new@gmail.com"))
        assert u is not None
        assert u.email_verified is True
        assert u.google_id == "g_99"
        assert u.credit == 100
        bonus = s.query(CreditTransaction).filter_by(user_id=u.id, reason="signup_bonus").count()
        assert bonus == 1


def test_google_links_existing_email_account():
    Session = get_session_factory()
    with Session() as s:
        existing = User(email="alice@e.com", username="alice",
                         password_hash=hash_password("supersecret"),
                         email_verified=False)
        s.add(existing); s.commit()
        eid = existing.id

    fake_info = {"email": "alice@e.com", "google_id": "g_77", "name": "Alice"}
    with patch("app.routers.auth.verify_google_id_token", return_value=fake_info):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "FAKE"})
    assert r.status_code == 200
    with Session() as s:
        u = s.get(User, eid)
        assert u.google_id == "g_77"
        assert u.email_verified is True


def test_google_returning_user_just_logs_in():
    Session = get_session_factory()
    with Session() as s:
        existing = User(email="bob@e.com", username="bob",
                         password_hash=hash_password("xxxxxxxx"),
                         email_verified=True, google_id="g_55")
        s.add(existing); s.commit()
        eid = existing.id
        existing_count = s.query(CreditTransaction).filter_by(user_id=eid).count()

    fake_info = {"email": "bob@e.com", "google_id": "g_55", "name": "Bob"}
    with patch("app.routers.auth.verify_google_id_token", return_value=fake_info):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "FAKE"})
    assert r.status_code == 200
    with Session() as s:
        new_count = s.query(CreditTransaction).filter_by(user_id=eid).count()
        assert new_count == existing_count  # no double bonus


def test_google_bad_token_returns_401():
    with patch("app.routers.auth.verify_google_id_token", side_effect=ValueError("bad")):
        c = _client()
        r = c.post("/api/v1/auth/google", json={"id_token": "BAD"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "bad_google_token"

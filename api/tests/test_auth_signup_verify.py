from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User


def _client():
    return TestClient(create_app())


def test_signup_creates_user_without_session_and_sends_email():
    sent = {}
    def fake_send(to, template, vars, subject):
        sent["to"] = to
        sent["template"] = template
        sent["vars"] = vars
        return True

    with patch("app.routers.auth.send_template", side_effect=fake_send):
        c = _client()
        r = c.post("/api/v1/auth/signup",
                   json={"username": "alice123", "email": "alice@e.com",
                         "password": "supersecret"})
        assert r.status_code == 201, r.text
        assert r.json() == {"ok": True, "email": "alice@e.com"}
        # Signup creates the user but does NOT issue a token — verify
        # email first. Was previously asserted via cookie absence; the
        # token-based equivalent is checking the response shape doesn't
        # include access_token.
        assert "access_token" not in r.json()

    assert sent["to"] == "alice@e.com"
    assert sent["template"] == "verify_email"
    assert "verify_url" in sent["vars"] and sent["vars"]["verify_url"].startswith("http")

    Session = get_session_factory()
    with Session() as s:
        from sqlalchemy import select
        u = s.scalar(select(User).where(User.email == "alice@e.com"))
        assert u is not None
        assert u.email_verified is False
        assert u.username == "alice123"
        assert u.credit == 0


def test_signup_rejects_duplicate_email():
    with patch("app.routers.auth.send_template", return_value=True):
        c = _client()
        c.post("/api/v1/auth/signup",
               json={"username": "alice123", "email": "alice@e.com", "password": "supersecret"})
        r = c.post("/api/v1/auth/signup",
                   json={"username": "alice456", "email": "alice@e.com", "password": "supersecret"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "email_taken"


def test_signup_rejects_duplicate_username():
    with patch("app.routers.auth.send_template", return_value=True):
        c = _client()
        c.post("/api/v1/auth/signup",
               json={"username": "alice", "email": "a@e.com", "password": "supersecret"})
        r = c.post("/api/v1/auth/signup",
                   json={"username": "alice", "email": "b@e.com", "password": "supersecret"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "username_taken"


def test_signup_rejects_bad_username():
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True):
        r = c.post("/api/v1/auth/signup",
                   json={"username": "a b", "email": "x@e.com", "password": "supersecret"})
    assert r.status_code == 422

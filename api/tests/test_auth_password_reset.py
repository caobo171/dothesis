from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth_tokens import make_reset_token, make_verify_token
from app.db import get_session_factory
from app.main import create_app
from app.models import Session as UserSession, User
from app.security import hash_password, verify_password


def _client():
    return TestClient(create_app())


def _seed(email, **kw):
    Session = get_session_factory()
    with Session() as s:
        u = User(email=email, username=email.split("@")[0],
                 password_hash=hash_password("oldpass1234"),
                 email_verified=True, **kw)
        s.add(u); s.commit(); return u.id


def test_forgot_unknown_email_returns_ok_no_send():
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/forgot-password", json={"email": "ghost@e.com"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    ms.assert_not_called()


def test_forgot_known_email_sends_template():
    _seed("alice@e.com")
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/forgot-password", json={"email": "alice@e.com"})
    assert r.status_code == 200
    ms.assert_called_once()
    args, kwargs = ms.call_args
    assert args[0] == "alice@e.com"
    assert args[1] == "reset_password"
    assert "reset_url" in args[2]

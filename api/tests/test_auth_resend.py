from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def _seed(email, **kw):
    Session = get_session_factory()
    with Session() as s:
        u = User(email=email, username=email.split("@")[0],
                 password_hash=hash_password("supersecret"), **kw)
        s.add(u); s.commit(); return u.id


def test_resend_for_unknown_email_is_ok_no_enumeration():
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "ghost@e.com"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    ms.assert_not_called()


def test_resend_for_verified_user_is_ok_no_send():
    _seed("done@e.com", email_verified=True)
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "done@e.com"})
    assert r.status_code == 200
    ms.assert_not_called()


def test_resend_sends_when_not_verified():
    _seed("u@e.com", email_verified=False)
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "u@e.com"})
    assert r.status_code == 200
    ms.assert_called_once()


def test_resend_throttled_within_60s():
    _seed("t@e.com", email_verified=False,
          last_verify_sent_at=datetime.now(timezone.utc))
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "t@e.com"})
    assert r.status_code == 429
    assert r.json()["detail"]["error"]["code"] == "throttled"
    ms.assert_not_called()


def test_resend_works_after_60s():
    _seed("over@e.com", email_verified=False,
          last_verify_sent_at=datetime.now(timezone.utc) - timedelta(seconds=70))
    c = _client()
    with patch("app.routers.auth.send_template", return_value=True) as ms:
        r = c.post("/api/v1/auth/resend-verification", json={"email": "over@e.com"})
    assert r.status_code == 200
    ms.assert_called_once()

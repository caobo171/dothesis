import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth_tokens import make_verify_token, make_reset_token
from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, User
from app.security import hash_password


def _client():
    return TestClient(create_app())


def _seed(email, **kw):
    Session = get_session_factory()
    with Session() as s:
        u = User(email=email, username=email.split("@")[0],
                 password_hash=hash_password("supersecret"), **kw)
        s.add(u)
        s.commit()
        return u.id


def test_verify_flips_flag_and_grants_bonus(monkeypatch):
    monkeypatch.setenv("DOTHESIS_SIGNUP_BONUS_CREDITS", "100")
    from app import settings as sm; sm._settings = None
    uid = _seed("alice@e.com", email_verified=False)
    tok = make_verify_token(uid)

    c = _client()
    r = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r.status_code == 200, r.text

    Session = get_session_factory()
    with Session() as s:
        u = s.get(User, uid)
        assert u.email_verified is True
        assert u.credit == 100
        tx = s.query(CreditTransaction).filter_by(user_id=uid).all()
        assert any(t.reason == "signup_bonus" for t in tx)


def test_verify_is_idempotent():
    uid = _seed("idem@e.com", email_verified=False)
    tok = make_verify_token(uid)
    c = _client()
    r1 = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r1.status_code == 200
    r2 = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r2.status_code == 200

    Session = get_session_factory()
    with Session() as s:
        u = s.get(User, uid)
        tx_count = s.query(CreditTransaction).filter_by(user_id=uid, reason="signup_bonus").count()
        assert tx_count == 1  # no double bonus
        assert u.credit == 100


def test_verify_rejects_reset_token():
    uid = _seed("x@e.com", email_verified=False)
    tok = make_reset_token(uid)  # wrong kind
    c = _client()
    r = c.post("/api/v1/auth/verify", json={"token": tok})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] in {"token_invalid", "token_mismatch"}


def test_verify_rejects_garbage_token():
    c = _client()
    r = c.post("/api/v1/auth/verify", json={"token": "not-a-real-token"})
    assert r.status_code == 400

import uuid
from sqlalchemy import select

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, User


@pytest.fixture
def admin_user():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


@pytest.fixture
def non_admin_user():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="alice@example.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_non_admin_gets_403(non_admin_user):
    client, app = _as(non_admin_user)
    try:
        r = client.get("/api/v1/admin/users")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_list_users(admin_user):
    Session = get_session_factory()
    with Session() as s:
        for i in range(3):
            s.add(User(email=f"u{i}@e.com", password_hash="x", credit=100*i))
        s.commit()

    client, app = _as(admin_user)
    try:
        r = client.get("/api/v1/admin/users?page=1&page_size=10")
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["total"] >= 4
        emails = {u["email"] for u in data["items"]}
        assert "cao.nv17@gmail.com" in emails
        assert "u1@e.com" in emails
    finally:
        app.dependency_overrides.clear()


def test_list_users_search(admin_user):
    Session = get_session_factory()
    with Session() as s:
        s.add(User(email="findme@example.com", password_hash="x", credit=0))
        s.commit()

    client, app = _as(admin_user)
    try:
        r = client.get("/api/v1/admin/users?q=findme")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["email"] == "findme@example.com"
    finally:
        app.dependency_overrides.clear()


def test_grant_credit_appends_ledger_and_updates_balance(admin_user):
    Session = get_session_factory()
    with Session() as s:
        target = User(email="target@e.com", password_hash="x", credit=50)
        s.add(target)
        s.commit()
        target_id = target.id

    client, app = _as(admin_user)
    try:
        r = client.post(f"/api/v1/admin/users/{target_id}/credit", json={"delta": 500, "note": "bonus"})
        assert r.status_code == 200, r.text
        with Session() as s:
            u = s.get(User, target_id)
            assert u.credit == 550
            tx = s.scalars(select(CreditTransaction).where(CreditTransaction.user_id == target_id)).all()
            assert len(tx) == 1
            assert tx[0].delta == 500
            assert tx[0].reason == "admin_grant"
    finally:
        app.dependency_overrides.clear()


def test_get_user_returns_detail(admin_user):
    Session = get_session_factory()
    with Session() as s:
        target = User(email="detail@e.com", password_hash="x", credit=42, username="dtl")
        s.add(target)
        s.commit()
        target_id = target.id

    client, app = _as(admin_user)
    try:
        r = client.get(f"/api/v1/admin/users/{target_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "detail@e.com"
        assert body["credit"] == 42
        assert body["username"] == "dtl"
    finally:
        app.dependency_overrides.clear()

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Announcement, User


@pytest.fixture
def regular_user():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="reader@e.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_me_returns_active_banner(regular_user):
    Session = get_session_factory()
    with Session() as s:
        s.add(Announcement(kind="login_banner", title="Hi", body="x", active=True))
        s.commit()

    client, app = _as(regular_user)
    try:
        r = client.get("/api/v1/announcements/me")
        assert r.status_code == 200
        data = r.json()
        assert data["login_banner"]["title"] == "Hi"
        assert data["first_login"] is None
    finally:
        app.dependency_overrides.clear()


def test_inactive_banner_not_returned(regular_user):
    Session = get_session_factory()
    with Session() as s:
        s.add(Announcement(kind="login_banner", title="Hidden", body="x", active=False))
        s.commit()

    client, app = _as(regular_user)
    try:
        r = client.get("/api/v1/announcements/me")
        assert r.status_code == 200
        assert r.json()["login_banner"] is None
    finally:
        app.dependency_overrides.clear()


def test_expired_banner_not_returned(regular_user):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    Session = get_session_factory()
    with Session() as s:
        s.add(Announcement(kind="login_banner", title="Old", body="x", active=True, ends_at=past))
        s.commit()

    client, app = _as(regular_user)
    try:
        r = client.get("/api/v1/announcements/me")
        assert r.status_code == 200
        assert r.json()["login_banner"] is None
    finally:
        app.dependency_overrides.clear()

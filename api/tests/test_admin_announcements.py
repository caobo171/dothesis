import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Announcement, User


@pytest.fixture
def admin():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", username="admin", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_create_and_list_announcement(admin):
    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/announcements", json={
            "kind": "login_banner",
            "title": "Welcome",
            "body": "Hello world",
            "active": True,
        })
        assert r.status_code == 201, r.text
        ann = r.json()
        assert ann["kind"] == "login_banner"

        # List read migrated GET /admin/announcements -> POST /admin/announcements/list.
        r2 = client.post("/api/v1/admin/announcements/list", json={})
        assert r2.status_code == 200
        items = r2.json()["items"]
        assert any(a["id"] == ann["id"] for a in items)
    finally:
        app.dependency_overrides.clear()


def test_patch_announcement(admin):
    Session = get_session_factory()
    with Session() as s:
        ann = Announcement(kind="first_login", title="Original", body="x", active=True)
        s.add(ann)
        s.commit()
        ann_id = ann.id

    client, app = _as(admin)
    try:
        r = client.patch(f"/api/v1/admin/announcements/{ann_id}", json={"title": "Updated"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated"
    finally:
        app.dependency_overrides.clear()


def test_delete_announcement(admin):
    Session = get_session_factory()
    with Session() as s:
        ann = Announcement(kind="first_login", title="Doomed", body="x", active=True)
        s.add(ann)
        s.commit()
        ann_id = ann.id

    client, app = _as(admin)
    try:
        r = client.delete(f"/api/v1/admin/announcements/{ann_id}")
        assert r.status_code == 204
        with Session() as s:
            assert s.get(Announcement, ann_id) is None
    finally:
        app.dependency_overrides.clear()


def test_bad_kind_rejected(admin):
    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/announcements", json={
            "kind": "nonsense", "title": "T", "body": "B", "active": True,
        })
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()

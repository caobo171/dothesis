"""Admin blog writes: the auth gate, seed validation and the duplicate block."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.blog import STATUS_PUBLISHED, seeds as S
from app.db import get_session_factory
from app.main import create_app
from app.models import BlogPost, User

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "docs" / "seo" / "fixtures" / "seeds"


@pytest.fixture
def db():
    with get_session_factory()() as s:
        yield s


@pytest.fixture
def categories(db):
    return S.upsert_categories(db, S.load_categories(FIXTURE_DIR))


@pytest.fixture
def seed():
    _, s = S.load_dir(FIXTURE_DIR)[0]
    body = copy.deepcopy(s)
    body["access_token"] = "test-token"  # AuthedBody requires the field to exist
    return body


def _client_as(email: str):
    app = create_app()
    from app.deps import current_user

    with get_session_factory()() as s:
        user = User(email=email, username=email.split("@")[0], password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


@pytest.fixture
def admin_client():
    client, app = _client_as("cao.nv17@gmail.com")
    yield client
    app.dependency_overrides.clear()


# --- the gate --------------------------------------------------------------

def test_admin_routes_reject_a_request_with_no_token():
    client = TestClient(create_app())
    r = client.post("/api/v1/admin/blog/list", json={})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "no_token"


def test_admin_routes_reject_a_signed_in_non_admin():
    client, app = _client_as("student@example.com")
    try:
        r = client.post("/api/v1/admin/blog/list", json={"access_token": "t"})
        assert r.status_code == 403
        assert r.json()["detail"]["error"]["code"] == "forbidden"
    finally:
        app.dependency_overrides.clear()


# --- upsert ----------------------------------------------------------------

def test_upsert_creates_a_post_from_a_seed(admin_client, seed, categories):
    r = admin_client.post("/api/v1/admin/blog/upsert", json=seed)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["action"] == "created"
    assert payload["slug"] == "cronbach-alpha-la-gi"
    assert payload["status"] == STATUS_PUBLISHED
    assert payload["category"]["slug"] == "spss"
    assert payload["reading_time"] >= 2


def test_upsert_updates_the_same_post_the_second_time(admin_client, seed, categories, db):
    admin_client.post("/api/v1/admin/blog/upsert", json=seed)
    seed["title"] = "Tiêu đề mới"
    r = admin_client.post("/api/v1/admin/blog/upsert", json=seed)
    assert r.json()["action"] == "updated"
    assert r.json()["title"] == "Tiêu đề mới"
    assert db.query(BlogPost).count() == 1


def test_upsert_rejects_an_invalid_seed(admin_client, seed, categories):
    seed["category"] = "khong-ton-tai"
    r = admin_client.post("/api/v1/admin/blog/upsert", json=seed)
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "invalid_seed"


def test_upsert_rejects_a_duplicate_intent(admin_client, seed, categories):
    admin_client.post("/api/v1/admin/blog/upsert", json=seed)

    clash = copy.deepcopy(seed)
    clash["slug"] = "he-so-cronbach-alpha-la-gi"
    clash["title"] = "Hệ số Cronbach's Alpha là gì"
    clash["focus_keyword"] = "hệ số cronbach alpha là gì"

    r = admin_client.post("/api/v1/admin/blog/upsert", json=clash)
    assert r.status_code == 409
    error = r.json()["detail"]["error"]
    assert error["code"] == "duplicate_intent"
    # The refusal has to be actionable on its own: which post, how close, on
    # what keyword, at what intent.
    assert "cronbach-alpha-la-gi" in error["message"]
    assert "%" in error["message"]
    assert "definition" in error["message"]


def test_a_long_enough_override_gets_the_duplicate_through(admin_client, seed, categories):
    admin_client.post("/api/v1/admin/blog/upsert", json=seed)

    clash = copy.deepcopy(seed)
    clash["slug"] = "he-so-cronbach-alpha-la-gi"
    clash["focus_keyword"] = "hệ số cronbach alpha là gì"
    clash["duplicate_override_reason"] = (
        "Bài này chỉ nói về thang đo hai biến quan sát, một trường hợp bài kia không xử lý.")

    r = admin_client.post("/api/v1/admin/blog/upsert", json=clash)
    assert r.status_code == 200, r.text
    assert r.json()["duplicate_override_reason"]
    # The clash is still reported, so the override is a decision, not a silence.
    assert [c["slug"] for c in r.json()["clashes"]] == ["cronbach-alpha-la-gi"]


def test_a_short_override_does_not(admin_client, seed, categories):
    admin_client.post("/api/v1/admin/blog/upsert", json=seed)
    clash = copy.deepcopy(seed)
    clash["slug"] = "he-so-cronbach-alpha-la-gi"
    clash["focus_keyword"] = "hệ số cronbach alpha là gì"
    clash["duplicate_override_reason"] = "vì tôi muốn"
    assert admin_client.post("/api/v1/admin/blog/upsert", json=clash).status_code == 409


def test_upsert_can_place_a_post_in_draft(admin_client, seed, categories):
    seed["status"] = 0
    r = admin_client.post("/api/v1/admin/blog/upsert", json=seed)
    assert r.json()["status"] == 0
    # ... and a draft is invisible to the public route.
    public = TestClient(create_app()).post(
        "/api/v1/blog/get", json={"slug": seed["slug"]})
    assert public.status_code == 404


# --- list and delete -------------------------------------------------------

def test_admin_list_shows_every_status(admin_client, seed, categories, db):
    db.add(BlogPost(locale="vi", slug="hidden", title="H", body="x", status=0,
                    created_at=datetime.now(timezone.utc)))
    db.commit()
    r = admin_client.post("/api/v1/admin/blog/list", json={"access_token": "t"}).json()
    assert "hidden" in {p["slug"] for p in r["posts"]}


def test_admin_list_filters_by_status(admin_client, seed, categories, db):
    admin_client.post("/api/v1/admin/blog/upsert", json=seed)
    r = admin_client.post("/api/v1/admin/blog/list",
                          json={"access_token": "t", "status": 0}).json()
    assert r["total"] == 0


def test_admin_delete_removes_the_post(admin_client, seed, categories, db):
    created = admin_client.post("/api/v1/admin/blog/upsert", json=seed).json()
    r = admin_client.post("/api/v1/admin/blog/delete",
                          json={"access_token": "t", "id": created["id"]})
    assert r.status_code == 200
    assert db.query(BlogPost).count() == 0


def test_admin_delete_reports_a_missing_post(admin_client):
    r = admin_client.post(
        "/api/v1/admin/blog/delete",
        json={"access_token": "t", "id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404

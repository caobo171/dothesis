"""SP6.5: editor API smoke + GET /chapters."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    # Mirror the exports test: enable orchestrator so m5_editor router is mounted.
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app(), follow_redirects=False)


def _create_user_and_set_cookie(client: TestClient) -> uuid.UUID:
    """Create a fresh user, set its session cookie on `client`, return user id."""
    sf = get_session_factory()
    with sf() as db:
        u = User(
            email=f"u{uuid.uuid4().hex[:6]}@x",
            username=f"u{uuid.uuid4().hex[:6]}",
            password_hash="x",
            email_verified=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        token = create_session(db, u)
    client.cookies.set("opendraft_session", token)
    return u.id


def _make_project_with_chapters(client: TestClient) -> str:
    """Create a project then seed two chapters directly into context_store.m5_writing."""
    from sqlalchemy.orm.attributes import flag_modified

    r = client.post("/api/v1/projects", json={"name": "X"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {
            "chapters": {
                "intro": {
                    "name": "intro",
                    "prose": "Hello world.",
                    "pending_edits": [],
                },
                "lit_review": {
                    "name": "lit_review",
                    "prose": "Lit body.",
                    "pending_edits": [],
                },
            }
        }
        flag_modified(cs, "m5_writing")
        db.commit()
    return pid


def test_get_chapters_returns_all(client):
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    r = client.get(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 200
    data = r.json()
    assert "intro" in data
    assert data["intro"]["prose"] == "Hello world."


def test_get_chapters_returns_empty_dict_when_no_m5(client):
    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]
    r = client.get(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 200
    assert r.json() == {}


def test_get_chapters_404_for_other_user(client):
    # User 1 creates the project.
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Switch client cookie to user 2.
    _create_user_and_set_cookie(client)
    r = client.get(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 404


def test_get_chapters_requires_auth(monkeypatch):
    # Use a fresh client with no cookies to confirm unauthenticated requests are blocked.
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    fresh_client = TestClient(create_app(), follow_redirects=False)
    fake = uuid.uuid4()
    r = fresh_client.get(f"/api/v1/projects/{fake}/m5/chapters")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PATCH /projects/{pid}/m5/chapters/{chapter_name} — autosave + revalidate
# ---------------------------------------------------------------------------

def test_patch_chapter_updates_prose(client):
    """PATCH with new prose → 200, response has new prose, DB is persisted."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    r = client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "Rewritten by user."},
    )
    assert r.status_code == 200
    # Decision: response body is the updated chapter dict
    assert r.json()["prose"] == "Rewritten by user."

    # Verify persistence in DB
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        assert cs.m5_writing["chapters"]["intro"]["prose"] == "Rewritten by user."


def test_patch_chapter_revalidates_citations(client):
    """Citations in prose are validated against the M2 reference pool."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed an M2 reference pool so (Smith, 2024) is known; (Unknown, 2023) is not
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {
            "research_gaps": [
                {"supporting_papers": [{"author": "Smith", "year": "2024"}]}
            ]
        }
        flag_modified(cs, "m2_literature")
        db.commit()

    r = client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "See (Smith, 2024) and (Unknown, 2023)."},
    )
    assert r.status_code == 200
    body = r.json()
    # Decision: only the known citation is recorded; the unknown one is flagged
    assert body["citations_used"] == ["(Smith, 2024)"]
    assert body["uncited_warnings"] == ["(Unknown, 2023)"]


def test_patch_unknown_chapter_returns_404(client):
    """Patching a chapter name not yet drafted (or unknown) returns 404."""
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # _make_project_with_chapters seeds only intro + lit_review; conclusion is absent
    r = client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/conclusion",
        json={"prose": "x"},
    )
    assert r.status_code == 404


def test_patch_chapter_404_for_other_user(client):
    """User B cannot PATCH a chapter that belongs to User A's project."""
    # User A creates the project and chapters
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Switch to User B
    _create_user_and_set_cookie(client)
    r = client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "intruder"},
    )
    assert r.status_code == 404

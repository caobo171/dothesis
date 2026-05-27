"""SP6.5: confirm every editor endpoint enforces ownership."""
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


# Decision: endpoint list updated after router inspection. Only 9 endpoints exist
# (removed GET /m5/chapters/intro which is not a separate route).
_ENDPOINTS_AND_METHODS = [
    ("GET",   "/m5/chapters",                       None),
    ("PATCH", "/m5/chapters/intro",                 {"prose": "x"}),
    ("GET",   "/m5/references",                     None),
    ("POST",  "/m5/chapters/intro/paraphrase",      {"from_offset": 0, "to_offset": 1}),
    ("POST",  "/m5/chapters/intro/translate",       {"from_offset": 0, "to_offset": 1, "target_lang": "vi"}),
    ("POST",  "/m5/chapters/intro/cite",            {"at_offset": 0, "reference_id": "x"}),
    ("POST",  "/m5/chapters/intro/pending/x/accept", None),
    ("POST",  "/m5/chapters/intro/pending/x/reject", None),
    ("POST",  "/m5/export",                          None),
]


@pytest.mark.parametrize("method,suffix,body", _ENDPOINTS_AND_METHODS)
def test_endpoint_requires_auth(method, suffix, body, monkeypatch):
    """Without auth headers: every endpoint rejects with 401 or 403."""
    # Use a fresh unauthenticated client to ensure no cookies from other tests.
    # Decision: each test creates its own client to ensure isolation.
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    fresh_client = TestClient(create_app(), follow_redirects=False)

    fake_pid = uuid.uuid4()
    url = f"/api/v1/projects/{fake_pid}{suffix}"
    r = fresh_client.request(method, url, json=body)
    assert r.status_code in (401, 403), (
        f"Expected 401/403 for unauthenticated {method} {suffix}, got {r.status_code}"
    )


@pytest.mark.parametrize("method,suffix,body", _ENDPOINTS_AND_METHODS)
def test_endpoint_404_for_other_user(method, suffix, body, client):
    """User A creates project; User B (different cookie) tries each endpoint.
    Should all return 404 to avoid leaking project existence."""
    # 1. Create user A and project
    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # 2. Switch client cookie to user B (different authenticated user)
    _create_user_and_set_cookie(client)

    # 3. User B attempts each endpoint on user A's project
    url = f"/api/v1/projects/{pid}{suffix}"
    r = client.request(method, url, json=body)
    assert r.status_code == 404, (
        f"Expected 404 for cross-user {method} {suffix}, got {r.status_code}: {r.text}"
    )

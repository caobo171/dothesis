"""SP6.5: documented concurrency model.

- Autosave PATCH = last-writer-wins (no optimistic-lock token).
- Accept on stale offsets = 409.
- Two accepts on the same edit = 404 on the second (already consumed).
"""
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
    # Mirror the test_m5_editor_router pattern: enable orchestrator so m5_editor router is mounted.
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


def _seed_pending_edit(pid: str, chapter: str, **overrides) -> dict:
    """Seed a hand-rolled pending edit directly into the chapter's ContextStore.

    Decision: bypasses the paraphrase/translate/cite endpoints so the test
    controls the exact offsets + texts without requiring LLM mocks. Returns
    the edit dict (with its id) so the caller can POST to the accept endpoint.
    """
    from datetime import datetime, timezone
    from uuid import uuid4
    from sqlalchemy.orm.attributes import flag_modified

    edit = {
        "id": uuid4().hex,
        "chapter_name": chapter,
        "from_offset": 0,
        "to_offset": 5,
        "old_text": "Hello",
        "new_text": "Greetings",
        "source": "paraphrase",
        "pending_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {},
    }
    edit.update(overrides)

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        ch = cs.m5_writing["chapters"][chapter]
        ch.setdefault("pending_edits", []).append(edit)
        flag_modified(cs, "m5_writing")
        db.commit()
    return edit


def test_double_accept_returns_404_on_second(client):
    """Accept once → 200 + edit consumed. Accept same id again → 404.

    Decision: the first accept splices the edit and removes it from pending_edits.
    The second accept finds no matching edit_id in pending_edits and returns 404
    with code='edit_not_found'.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed one pending edit
    edit = _seed_pending_edit(pid, "intro")
    edit_id = edit["id"]

    # First accept should succeed
    r1 = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/accept")
    assert r1.status_code == 200, f"First accept failed: {r1.text}"
    assert r1.json()["prose"] == "Greetings world."

    # Second accept on the same edit_id should fail with 404 (edit already consumed)
    r2 = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/accept")
    assert r2.status_code == 404, f"Expected 404 on second accept, got {r2.status_code}: {r2.text}"
    assert r2.json()["detail"]["error"]["code"] == "edit_not_found"


def test_patch_after_accept_overwrites_last_writer_wins(client):
    """Documents last-writer-wins: autosave PATCH after accept clobbers
    the spliced prose.

    Decision: this demonstrates the concurrency model accepts this race condition
    in single-user/single-tab mode. If the user edits the chapter while pending
    edits are being accepted, the PATCH (last writer) wins. This is acceptable
    because the pending edit has already been consumed; the user's manual edit
    takes final precedence.
    """
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed one pending edit (Hello → Greetings)
    edit = _seed_pending_edit(pid, "intro")
    edit_id = edit["id"]

    # Accept the edit: prose becomes "Greetings world."
    r1 = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/accept")
    assert r1.status_code == 200
    assert r1.json()["prose"] == "Greetings world."

    # Now PATCH with different prose: last writer wins
    r2 = client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "Original draft."},
    )
    assert r2.status_code == 200
    assert r2.json()["prose"] == "Original draft."

    # Verify persistence in fresh session
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        prose = cs.m5_writing["chapters"]["intro"]["prose"]
        assert prose == "Original draft.", f"Expected 'Original draft.' but got '{prose}'"


def test_accept_with_shifted_prose_returns_409(client):
    """When prose has been changed externally so old_text no longer matches:
    Accept returns 409 + edit NOT consumed.

    Decision: the 409 stale_offsets check validates that prose[from_offset:to_offset]
    still equals the edit's old_text before accepting. If the prose was mutated
    after the edit was created the offsets are stale and splicing would corrupt
    the document. The edit remains in pending_edits so it can be rejected or
    re-validated manually.
    """
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed one pending edit expecting 'Hello' at offsets 0..5
    edit = _seed_pending_edit(
        pid,
        "intro",
        from_offset=0,
        to_offset=5,
        old_text="Hello",
        new_text="Greetings",
    )
    edit_id = edit["id"]

    # Mutate the prose so offsets are stale (no longer starts with "Hello")
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing["chapters"]["intro"]["prose"] = "Modified world."
        flag_modified(cs, "m5_writing")
        db.commit()

    # Accept with stale offsets → 409
    r = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/accept")
    assert r.status_code == 409, f"Expected 409 on stale offsets, got {r.status_code}: {r.text}"
    detail = r.json()["detail"]
    assert detail["error"]["code"] == "stale_offsets"

    # The edit must NOT be consumed; verify it still exists in pending_edits
    sf2 = get_session_factory()
    with sf2() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        remaining = cs.m5_writing["chapters"]["intro"]["pending_edits"]
        ids = [e["id"] for e in remaining]
        assert edit_id in ids, "stale 409 must NOT remove the edit from pending_edits"

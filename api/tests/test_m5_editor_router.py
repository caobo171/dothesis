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


# ---------------------------------------------------------------------------
# GET /projects/{pid}/m5/references — M2 reference pool with stable ids
# ---------------------------------------------------------------------------


def test_get_references_returns_dedup_m2_pool(client):
    """GET /m5/references returns deduped M2 pool with stable hash ids."""
    from sqlalchemy.orm.attributes import flag_modified

    # 1. Create authenticated user + project
    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    assert r.status_code == 200
    pid = r.json()["id"]

    # 2. Seed M2 ref pool with two research gaps; one gap has a duplicate paper
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {
            "research_gaps": [
                {
                    "supporting_papers": [
                        {"author": "Smith", "year": "2024", "title": "A"},
                        {"author": "Jones", "year": "2023", "title": "B"},
                    ]
                },
                {
                    "supporting_papers": [
                        {"author": "Smith", "year": "2024", "title": "A"},  # duplicate
                    ]
                },
            ]
        }
        flag_modified(cs, "m2_literature")
        db.commit()

    # 3. GET /m5/references
    r = client.get(f"/api/v1/projects/{pid}/m5/references")
    assert r.status_code == 200
    refs = r.json()

    # 4. Assert deduplication + stable ids
    assert len(refs) == 2, f"Expected 2 deduplicated references, got {len(refs)}: {refs}"
    # All refs should have "id" key
    assert all("id" in ref for ref in refs), f"All refs must have 'id' key: {refs}"
    # Extract (author, year) pairs to verify dedup
    authors_years = {(ref["author"], ref["year"]) for ref in refs}
    assert authors_years == {("Smith", "2024"), ("Jones", "2023")}


def test_get_references_returns_empty_when_no_m2(client):
    """GET /m5/references returns [] when no M2 pool exists."""
    # Create authenticated user + project (no M2 seeding)
    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    assert r.status_code == 200
    pid = r.json()["id"]

    # GET /m5/references on empty project
    r = client.get(f"/api/v1/projects/{pid}/m5/references")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# POST /projects/{pid}/m5/chapters/{chapter_name}/paraphrase — inline AI
# ---------------------------------------------------------------------------

from unittest.mock import patch  # noqa: E402 — may already be imported at top via monkeypatch


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_creates_pending_edit(mock_llm, client):
    """Mock the LLM, paraphrase a selection, verify PendingEdit landed in chapter.

    Decision: the test overrides the default intro prose with a full sentence so
    from_offset / to_offset can be computed deterministically via str.index().
    """
    from sqlalchemy.orm.attributes import flag_modified

    mock_llm.return_value = "A growing body of work suggests"

    # 1. Authenticate + create project + seed chapters
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # 2. Overwrite the intro prose with the target sentence we'll select from
    full_prose = "The literature is broad. Recent studies have shown that algo decisions matter."
    target = "Recent studies have shown"
    from_o = full_prose.index(target)
    to_o = from_o + len(target)

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing["chapters"]["intro"]["prose"] = full_prose
        flag_modified(cs, "m5_writing")
        db.commit()

    # 3. POST paraphrase
    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/paraphrase",
        json={"from_offset": from_o, "to_offset": to_o, "style": "more formal"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # 4. Response shape assertions
    assert body["source"] == "paraphrase"
    assert body["new_text"] == "A growing body of work suggests"
    assert body["old_text"] == target
    assert body["from_offset"] == from_o
    assert body["to_offset"] == to_o

    # 5. Verify PendingEdit persisted into ContextStore
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        pending = cs.m5_writing["chapters"]["intro"]["pending_edits"]
        assert len(pending) == 1
        assert pending[0]["source"] == "paraphrase"
        assert pending[0]["new_text"] == "A growing body of work suggests"


def test_paraphrase_404_unknown_chapter(client):
    """POSTing to a chapter name that was never seeded returns 404.

    Decision: _make_project_with_chapters seeds only intro + lit_review;
    conclusion is absent so the endpoint should respond with 404.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/conclusion/paraphrase",
        json={"from_offset": 0, "to_offset": 5},
    )
    assert r.status_code == 404


def test_paraphrase_offsets_out_of_range_returns_400(client):
    """Offsets that exceed prose length return 400 with offset_out_of_range.

    Decision: _make_project_with_chapters seeds intro with 'Hello world.' (12 chars).
    to_offset=9999 is far past the end, so the validation guard must fire before
    the LLM is called.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/paraphrase",
        json={"from_offset": 0, "to_offset": 9999},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /projects/{pid}/m5/chapters/{chapter_name}/translate — inline AI
# ---------------------------------------------------------------------------


@patch("orchestrator.tools.m5_inline._call_llm")
def test_translate_creates_pending_edit_with_target_lang(mock_llm, client):
    """Mock the LLM, translate a selection, verify PendingEdit landed with target_lang.

    Decision: mirrors the paraphrase test pattern. The endpoint creates a PendingEdit
    (not an accepted edit) so the front-end can present an accept/reject ribbon.
    The metadata dict includes target_lang so the client can reconstruct the operation.
    """
    from sqlalchemy.orm.attributes import flag_modified

    mock_llm.return_value = "Một nghiên cứu gần đây"

    # 1. Authenticate + create project + seed chapters
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # 2. Overwrite the intro prose with the target sentence we'll select from
    full_prose = "The literature is broad. Recent studies have shown that algo decisions matter."
    target = "Recent studies have shown"
    from_o = full_prose.index(target)
    to_o = from_o + len(target)

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing["chapters"]["intro"]["prose"] = full_prose
        flag_modified(cs, "m5_writing")
        db.commit()

    # 3. POST translate with target_lang
    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/translate",
        json={"from_offset": from_o, "to_offset": to_o, "target_lang": "vi"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # 4. Response shape assertions
    assert body["source"] == "translate"
    assert body["new_text"] == "Một nghiên cứu gần đây"
    assert body["old_text"] == target
    assert body["from_offset"] == from_o
    assert body["to_offset"] == to_o
    assert body["metadata"]["target_lang"] == "vi"

    # 5. Verify PendingEdit persisted into ContextStore
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        pending = cs.m5_writing["chapters"]["intro"]["pending_edits"]
        assert len(pending) == 1
        assert pending[0]["source"] == "translate"
        assert pending[0]["new_text"] == "Một nghiên cứu gần đây"
        assert pending[0]["metadata"]["target_lang"] == "vi"


def test_translate_400_on_missing_target_lang(client):
    """Missing target_lang field returns 422 via FastAPI body validation.

    Decision: This is a required field in TranslateBody, so FastAPI rejects the
    request before it reaches the endpoint handler.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/translate",
        json={"from_offset": 0, "to_offset": 5},  # target_lang is missing
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /projects/{pid}/m5/chapters/{chapter_name}/cite — inline citations
# ---------------------------------------------------------------------------


def test_cite_inserts_pending_edit_with_canonical_text(client):
    """Cite a paper from M2 pool → PendingEdit with canonical (Author, Year) text.

    Decision: cite differs from paraphrase/translate — it's an INSERTION (not
    replacement). from_offset == to_offset == at_offset, old_text="", new_text
    has a leading space to ensure whitespace between prose and citation.
    """
    from sqlalchemy.orm.attributes import flag_modified

    # 1. Authenticate + create project + seed chapters
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # 2. Seed M2 reference pool with one paper
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

    # 3. GET /m5/references to retrieve the assigned reference id
    r = client.get(f"/api/v1/projects/{pid}/m5/references")
    assert r.status_code == 200
    refs = r.json()
    assert len(refs) == 1
    ref_id = refs[0]["id"]

    # 4. POST /m5/chapters/intro/cite at offset 5 ("Hello world."; offset 5 is after "Hello")
    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 5, "reference_id": ref_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # 5. Response body assertions
    assert body["source"] == "cite"
    assert body["new_text"] == " (Smith, 2024)", f"Expected leading space in '{body['new_text']}'"
    assert body["old_text"] == ""
    assert body["from_offset"] == 5
    assert body["to_offset"] == 5
    assert body["metadata"]["reference_id"] == ref_id

    # 6. Verify PendingEdit persisted into ContextStore
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        pending = cs.m5_writing["chapters"]["intro"]["pending_edits"]
        assert len(pending) == 1
        assert pending[0]["source"] == "cite"
        assert pending[0]["new_text"] == " (Smith, 2024)"
        assert pending[0]["metadata"]["reference_id"] == ref_id


def test_cite_404_on_unknown_reference(client):
    """POSTing cite with a nonexistent reference_id returns 404.

    Decision: _make_project_with_chapters creates a project with chapters but
    does not seed M2 references, so any reference_id lookup will fail.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 0, "reference_id": "nonexistent"},
    )
    assert r.status_code == 404

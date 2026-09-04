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
    client.headers["Authorization"] = f"Bearer {token}"
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
    r = client.post(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 200
    data = r.json()
    assert "intro" in data
    assert data["intro"]["prose"] == "Hello world."


def test_get_chapters_returns_empty_dict_when_no_m5(client):
    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 200
    assert r.json() == {}


def test_get_chapters_backfills_from_final_sections(client):
    # A project whose M5 went through the conversational/export path: prose in
    # final_sections, no chapters. The editor must still open with content, so
    # list_chapters synthesizes + persists the canonical chapter dict.
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {
            "final_sections": [
                {"chapter_name": "intro", "title": "Chapter 1 — Introduction", "prose": "Intro prose here."},
                {"title": "Chapter 2 — Literature Review", "prose": "Lit prose here."},
                {"title": "References", "prose": "Doe, J. (2024)."},
            ]
        }
        flag_modified(cs, "m5_writing")
        db.commit()

    r = client.post(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 200
    data = r.json()
    # intro mapped via chapter_name, lit_review via title reverse-lookup.
    assert data["intro"]["prose"] == "Intro prose here."
    assert data["lit_review"]["prose"] == "Lit prose here."
    # References is not an editable chapter — dropped.
    assert "References" not in data
    assert len(data) == 2

    # Persisted: a second call reads chapters directly (no re-synthesis needed).
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        assert "intro" in cs.m5_writing["chapters"]
        assert "lit_review" in cs.m5_writing["chapters"]


def test_get_chapters_404_for_other_user(client):
    # User 1 creates the project.
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Switch client cookie to user 2.
    _create_user_and_set_cookie(client)
    r = client.post(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 404


def test_get_chapters_requires_auth(monkeypatch):
    # Use a fresh client with no cookies to confirm unauthenticated requests are blocked.
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    fresh_client = TestClient(create_app(), follow_redirects=False)
    fake = uuid.uuid4()
    r = fresh_client.post(f"/api/v1/projects/{fake}/m5/chapters")
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
    r = client.post(f"/api/v1/projects/{pid}/m5/references")
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
    r = client.post(f"/api/v1/projects/{pid}/m5/references")
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


@pytest.mark.parametrize("kind", ["proofread", "improve", "humanize", "expand", "shorten"])
@patch("orchestrator.tools.m5_inline._call_llm")
def test_inline_rewrite_actions_create_pending_edit(mock_llm, client, kind):
    """The jenni-style inline actions each rewrite the selection via the shared
    rewrite tool and land a PendingEdit tagged with that action's source."""
    from sqlalchemy.orm.attributes import flag_modified

    mock_llm.return_value = "the rewritten selection"

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

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

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/{kind}",
        json={"from_offset": from_o, "to_offset": to_o},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == kind
    assert body["new_text"] == "the rewritten selection"
    assert body["old_text"] == target

    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        pending = cs.m5_writing["chapters"]["intro"]["pending_edits"]
        assert len(pending) == 1 and pending[0]["source"] == kind


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
    r = client.post(f"/api/v1/projects/{pid}/m5/references")
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


# ---------------------------------------------------------------------------
# POST /projects/{pid}/m5/chapters/{chapter_name}/pending/{edit_id}/accept
# ---------------------------------------------------------------------------


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


def test_accept_splices_new_text_and_drops_edit(client):
    """1. Seed chapter with prose 'Hello world.' AND a pending_edit (from 0..5, old='Hello', new='Greetings').
    2. POST /m5/chapters/intro/pending/{edit_id}/accept
    3. Assert 200; response chapter has prose='Greetings world.' and pending_edits=[].

    Decision: _make_project_with_chapters seeds intro with 'Hello world.' so
    the offsets 0..5 exactly cover 'Hello'. The accept endpoint must splice
    new_text in place and clear the edit from pending_edits.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed the pending edit (offsets 0..5 = 'Hello' in 'Hello world.')
    edit = _seed_pending_edit(
        pid,
        "intro",
        from_offset=0,
        to_offset=5,
        old_text="Hello",
        new_text="Greetings",
    )
    edit_id = edit["id"]

    r = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/accept")
    assert r.status_code == 200, r.text
    body = r.json()

    # Prose must be spliced; pending_edits must be empty
    assert body["prose"] == "Greetings world."
    assert body["pending_edits"] == []

    # Verify DB persistence
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        ch = cs.m5_writing["chapters"]["intro"]
        assert ch["prose"] == "Greetings world."
        assert ch["pending_edits"] == []


def test_accept_409_on_stale_offsets(client):
    """1. Seed pending_edit (old_text='Hello') but mutate prose AFTER (e.g. 'DIFFERENT world.').
    2. POST .../accept
    3. Assert 409, response detail.error.code == 'stale_offsets'.

    Decision: the stale check compares prose[from_offset:to_offset] against
    the edit's old_text. If they differ the prose was modified after the edit
    was created and accepting it would corrupt the document.
    """
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed edit expecting 'Hello' at 0..5
    edit = _seed_pending_edit(
        pid,
        "intro",
        from_offset=0,
        to_offset=5,
        old_text="Hello",
        new_text="Greetings",
    )
    edit_id = edit["id"]

    # Mutate the prose so offsets are stale (the chapter now starts with 'DIFFERENT')
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing["chapters"]["intro"]["prose"] = "DIFFERENT world."
        flag_modified(cs, "m5_writing")
        db.commit()

    r = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/accept")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"]["code"] == "stale_offsets"

    # Decision: the edit must NOT be consumed on 409; peek happens before pop so
    # the edit stays in pending_edits and can still be rejected via /reject.
    sf2 = get_session_factory()
    with sf2() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        remaining = cs.m5_writing["chapters"]["intro"]["pending_edits"]
        ids = [e["id"] for e in remaining]
        assert edit_id in ids, "stale 409 must NOT remove the edit from pending_edits"


def test_accept_404_on_unknown_edit(client):
    """POST /m5/chapters/intro/pending/nonexistent/accept → 404.

    Decision: the endpoint must return 404 (not 500 or 422) when the edit_id
    does not exist in the chapter's pending_edits list.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/nonexistent/accept"
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"]["code"] == "edit_not_found"


# ---------------------------------------------------------------------------
# POST /projects/{pid}/m5/chapters/{chapter_name}/pending/{edit_id}/reject
# ---------------------------------------------------------------------------


def test_reject_drops_edit_without_touching_prose(client):
    """1. Seed chapter with prose 'Hello world.' AND a pending_edit (from 0..5, old='Hello', new='Greetings').
    2. POST /m5/chapters/intro/pending/{edit_id}/reject
    3. Assert 200; response chapter has prose='Hello world.' UNCHANGED + pending_edits=[].

    Decision: reject is simpler than accept — it drops the edit without any
    offset validation or prose mutation. The original prose stays unchanged.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed the pending edit (offsets 0..5 = 'Hello' in 'Hello world.')
    edit = _seed_pending_edit(
        pid,
        "intro",
        from_offset=0,
        to_offset=5,
        old_text="Hello",
        new_text="Greetings",
    )
    edit_id = edit["id"]

    r = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/reject")
    assert r.status_code == 200, r.text
    body = r.json()

    # Prose must be unchanged; pending_edits must be empty
    assert body["prose"] == "Hello world."
    assert body["pending_edits"] == []

    # Verify DB persistence
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        ch = cs.m5_writing["chapters"]["intro"]
        assert ch["prose"] == "Hello world."
        assert ch["pending_edits"] == []


def test_reject_404_on_unknown_edit(client):
    """POST /m5/chapters/intro/pending/nope/reject → 404.

    Decision: the endpoint must return 404 when the edit_id does not exist
    in the chapter's pending_edits list, mirroring the accept endpoint behavior.
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/nope/reject"
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"]["code"] == "edit_not_found"


# ---------------------------------------------------------------------------
# chapter_name guard: accept + reject must 404 when edit belongs to a different chapter
# ---------------------------------------------------------------------------


def test_accept_404_when_edit_id_belongs_to_other_chapter(client):
    """Critical: an edit_id from a different chapter should not be acceptable via wrong URL.

    Decision: this validates the chapter_name guard added to accept_pending_edit.
    If a bug ever places an edit in the wrong chapter's pending_edits, it must not
    be consumable via a URL pointing to a different chapter.

    Seed an edit on lit_review, then POST accept via the intro URL → 404.
    Re-fetch ContextStore: the edit must STILL be on lit_review (not consumed).
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed an edit on lit_review ("Lit body." → "Lit content.")
    edit = _seed_pending_edit(
        pid,
        "lit_review",
        from_offset=0,
        to_offset=3,
        old_text="Lit",
        new_text="Lit content",
        chapter_name="lit_review",
    )
    edit_id = edit["id"]

    # Attempt to accept via the WRONG chapter URL (intro instead of lit_review)
    r = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/accept")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"]["code"] == "edit_not_found"

    # Critical: the edit must still be present on lit_review — not consumed
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        lit_edits = cs.m5_writing["chapters"]["lit_review"]["pending_edits"]
        ids = [e["id"] for e in lit_edits]
        assert edit_id in ids, "Wrong-chapter 404 must NOT consume the edit from lit_review"


def test_reject_404_when_edit_id_belongs_to_other_chapter(client):
    """Critical: an edit_id from a different chapter should not be rejectable via wrong URL.

    Decision: this validates the chapter_name guard added to reject_pending_edit.
    Mirrors the accept variant — both accept and reject must guard against cross-chapter
    edit consumption.

    Seed an edit on lit_review, then POST reject via the intro URL → 404.
    Re-fetch ContextStore: the edit must STILL be on lit_review (not consumed).
    """
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    # Seed an edit on lit_review ("Lit body." → "Literature review body.")
    edit = _seed_pending_edit(
        pid,
        "lit_review",
        from_offset=0,
        to_offset=3,
        old_text="Lit",
        new_text="Literature",
        chapter_name="lit_review",
    )
    edit_id = edit["id"]

    # Attempt to reject via the WRONG chapter URL (intro instead of lit_review)
    r = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit_id}/reject")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"]["code"] == "edit_not_found"

    # Critical: the edit must still be present on lit_review — not consumed
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        lit_edits = cs.m5_writing["chapters"]["lit_review"]["pending_edits"]
        ids = [e["id"] for e in lit_edits]
        assert edit_id in ids, "Wrong-chapter 404 must NOT consume the edit from lit_review"


# ---------------------------------------------------------------------------
# POST /projects/{pid}/m5/export — re-run compile_pdf + export_docx (SP6.5)
# ---------------------------------------------------------------------------


def _make_project_with_all_chapters(client: TestClient) -> str:
    """Create a project then seed ALL 6 chapters into context_store.m5_writing.

    Decision: export requires all 6 chapters; this helper is separate from
    _make_project_with_chapters (which only seeds 2) so the incomplete-chapters
    400 test can reuse _make_project_with_chapters without modification.
    """
    from sqlalchemy.orm.attributes import flag_modified

    r = client.post("/api/v1/projects", json={"name": "Export test project"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {
            "chapters": {
                "intro":       {"name": "intro",       "prose": "Introduction prose.",   "pending_edits": []},
                "lit_review":  {"name": "lit_review",  "prose": "Lit review prose.",     "pending_edits": []},
                "methodology": {"name": "methodology", "prose": "Methodology prose.",    "pending_edits": []},
                "results":     {"name": "results",     "prose": "Results prose.",        "pending_edits": []},
                "discussion":  {"name": "discussion",  "prose": "Discussion prose.",     "pending_edits": []},
                "conclusion":  {"name": "conclusion",  "prose": "Conclusion prose.",     "pending_edits": []},
            }
        }
        flag_modified(cs, "m5_writing")
        db.commit()
    return pid


@patch("app.routers.m5_editor.run_export")
def test_export_runs_both_compilers_and_returns_artifacts(mock_run_export, client):
    """1. Mock run_export → [docx artifact, pdf artifact]
    2. Auth + create project + seed ALL 6 chapters
    3. POST /api/v1/projects/{pid}/m5/export
    4. Assert 200; body has docx.s3_key + pdf.size_bytes + docx.download_url
    5. Assert run_export called exactly once

    Decision: the router now delegates to the shared `run_export` helper
    (orchestrator.tools.m5_writing) instead of calling compile_pdf/export_docx
    directly — one export path shared by the auto-export hook, this route, and
    the agent's export tool. Patch in the router's namespace because it does
    `from orchestrator.tools.m5_writing import run_export` at import time.
    """
    mock_run_export.return_value = [
        {"kind": "docx", "s3_key": "projects/p/exports/thesis.docx", "size_bytes": 1234,
         "download_url": "/api/v1/projects/p/exports/thesis.docx", "uri": ""},
        {"kind": "pdf",  "s3_key": "projects/p/exports/thesis.pdf",  "size_bytes": 5678,
         "download_url": "/api/v1/projects/p/exports/thesis.pdf", "uri": ""},
    ]

    _create_user_and_set_cookie(client)
    pid = _make_project_with_all_chapters(client)

    r = client.post(f"/api/v1/projects/{pid}/m5/export")
    assert r.status_code == 200, r.text
    body = r.json()

    # Shape: top-level "docx" and "pdf" keys
    assert "docx" in body, f"Missing 'docx' key: {body}"
    assert "pdf"  in body, f"Missing 'pdf' key: {body}"

    # Check docx artifact fields
    assert body["docx"]["s3_key"] == "projects/p/exports/thesis.docx"
    assert body["docx"]["size_bytes"] == 1234
    # download_url is the relative redirect path to the exports endpoint
    assert "thesis.docx" in body["docx"]["download_url"]

    # Check pdf artifact fields
    assert body["pdf"]["s3_key"] == "projects/p/exports/thesis.pdf"
    assert body["pdf"]["size_bytes"] == 5678

    mock_run_export.assert_called_once()


@patch("app.routers.m5_editor.run_export")
def test_export_renders_partial_chapters(mock_run_export, client):
    """Pivot: a partial draft (only intro + lit_review) now EXPORTS — the thesis
    is written chapter by chapter as each module completes, so the docx reflects
    whatever exists. The response names the chapters still to draft.
    """
    mock_run_export.return_value = [
        {"kind": "docx", "s3_key": "k.docx", "size_bytes": 1, "download_url": "/x", "uri": ""},
        {"kind": "pdf",  "s3_key": "k.pdf",  "size_bytes": 1, "download_url": "/y", "uri": ""},
    ]
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)  # intro + lit_review only

    r = client.post(f"/api/v1/projects/{pid}/m5/export")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "docx" in body and "pdf" in body
    assert set(body["missing_chapters"]) == {"methodology", "results", "discussion", "conclusion"}
    mock_run_export.assert_called_once()


def test_export_400_when_no_chapters_yet(client):
    """The only remaining export gate: nothing drafted at all → 400 no_chapters_yet
    (there is no prose to render into a document)."""
    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "empty"})
    pid = r.json()["id"]

    r = client.post(f"/api/v1/projects/{pid}/m5/export")
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"]["code"] == "no_chapters_yet"

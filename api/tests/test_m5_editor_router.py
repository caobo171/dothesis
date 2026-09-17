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


@pytest.fixture(autouse=True)
def _isolated_research_cache(monkeypatch, tmp_path):
    # Cache behavior is tested locally; never let another test or a developer's
    # persisted search result suppress this test's mocked provider call.
    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(tmp_path / "research-cache"))


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


def test_get_chapters_attaches_reversible_image_preview(client, tmp_path):
    """Local export artifacts render in editor without rewriting stored prose."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]
    image = tmp_path / "model.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\npreview")
    prose = f"**Figure 3.1**\n\n![Research model]({image})"

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {"chapters": {"methodology": {
            "name": "methodology", "prose": prose, "pending_edits": [],
        }}}
        flag_modified(cs, "m5_writing")
        db.commit()

    r = client.post(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 200
    chapter = r.json()["methodology"]
    assert chapter["prose"] == prose
    assert chapter["media"][0]["source"] == str(image)
    assert chapter["media"][0]["preview_url"].startswith("data:image/png;base64,")
    assert chapter["renderable_tokens"] == []

    with sf() as db:
        stored = (db.get(ContextStore, uuid.UUID(pid)).m5_writing or {})["chapters"]
        assert stored["methodology"]["prose"] == prose
        assert "media" not in stored["methodology"]
        assert "renderable_tokens" not in stored["methodology"]


def test_get_chapters_marks_data_cleaning_renderable_only_with_verified_state(client):
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {"chapters": {"methodology": {
            "name": "methodology", "prose": "[[DT:data_cleaning]]", "pending_edits": [],
        }}}
        cs.m4_analysis = {"analysis_results": {"data_screening": {
            "n_before": 300, "n_after": 286, "missing_removed": 14,
        }}}
        flag_modified(cs, "m5_writing")
        flag_modified(cs, "m4_analysis")
        db.commit()

    r = client.post(f"/api/v1/projects/{pid}/m5/chapters")
    assert r.status_code == 200
    assert r.json()["methodology"]["renderable_tokens"] == ["data_cleaning"]


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


def test_get_chapters_backfill_keeps_both_legacy_closing_chapters(client):
    # The permanence case: list_chapters COMMITS what it synthesizes, and every
    # later read prefers `chapters`. So if the backfill dropped a pre-branch
    # project's discussion prose, opening the editor once would make the loss
    # permanent. Chapter 5 must hold both blocks, discussion first, with the
    # limitations token intact — and no un-PATCHable `discussion` pane.
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {
            "final_sections": [
                {"chapter_name": "intro", "title": "Chapter 1 — Introduction",
                 "prose": "Intro prose here."},
                {"title": "Chapter 5 — Discussion",
                 "prose": "Discussion prose with [[DT:limitations]]."},
                {"title": "Chapter 6 — Conclusion", "prose": "Closing remarks."},
            ]
        }
        flag_modified(cs, "m5_writing")
        db.commit()

    data = client.post(f"/api/v1/projects/{pid}/m5/chapters").json()
    assert set(data) == {"intro", "conclusion"}
    assert data["conclusion"]["prose"] == (
        "Discussion prose with [[DT:limitations]].\n\nClosing remarks.")

    # Committed in that shape, and the surviving keys are all PATCH-able
    # (_VALID_CHAPTER_NAMES) so autosave cannot 404 on a rendered pane.
    from app.routers.m5_editor import _VALID_CHAPTER_NAMES
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        stored = cs.m5_writing["chapters"]
        assert set(stored) <= _VALID_CHAPTER_NAMES
        assert "[[DT:limitations]]" in stored["conclusion"]["prose"]


def test_get_chapters_normalizes_a_stored_retired_key(client):
    # A pre-branch AUTO-MODE project stored all six keys in `chapters` — the
    # backfill above never runs for it, because `chapters` is already there.
    # Returning that dict raw left its `discussion` prose invisible and
    # uneditable in the editor (OutlineRail knows only the canonical five) while
    # sections_from_m5_slice still shipped it in the export, so editor and
    # exported document disagreed about Chapter 5 for exactly that cohort.
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {"chapters": {
            "intro": {"name": "intro", "prose": "Intro prose.", "pending_edits": []},
            "discussion": {"name": "discussion",
                           "prose": "Discussion prose with [[DT:limitations]].",
                           "pending_edits": []},
            "conclusion": {"name": "conclusion", "prose": "Closing remarks.",
                           "pending_edits": []},
        }}
        flag_modified(cs, "m5_writing")
        db.commit()

    data = client.post(f"/api/v1/projects/{pid}/m5/chapters").json()
    assert set(data) == {"intro", "conclusion"}
    assert data["conclusion"]["prose"] == (
        "Discussion prose with [[DT:limitations]].\n\nClosing remarks.")
    assert data["conclusion"]["name"] == "conclusion"

    # Committed in the normalized shape, so the next read is a plain one and the
    # surviving keys are all PATCH-able.
    from app.routers.m5_editor import _VALID_CHAPTER_NAMES
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        stored = cs.m5_writing["chapters"]
        assert set(stored) == {"intro", "conclusion"}
        assert set(stored) <= _VALID_CHAPTER_NAMES
        assert "[[DT:limitations]]" in stored["conclusion"]["prose"]


def test_get_chapters_normalization_keeps_a_chapter_the_student_emptied(client):
    # Normalization COMMITS, so anything it fails to carry forward is deleted
    # from persisted state by a plain read. `merge_chapter_prose` returns only
    # the chapters it claims — blank prose is skipped — so a chapter the student
    # cleared in the editor was dropped on the next open: the pane disappeared
    # (presentNames filters on the returned keys) and autosave 404'd
    # chapter_not_drafted, i.e. the chapter became unrecoverable.
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {"chapters": {
            "intro": {"name": "intro", "prose": "Intro prose.", "pending_edits": []},
            "results": {"name": "results", "prose": "", "pending_edits": []},
            "discussion": {"name": "discussion", "prose": "Discussion prose.",
                           "pending_edits": []},
            "conclusion": {"name": "conclusion", "prose": "Closing remarks.",
                           "pending_edits": []},
        }}
        flag_modified(cs, "m5_writing")
        db.commit()

    data = client.post(f"/api/v1/projects/{pid}/m5/chapters").json()
    # The retired key folds; the emptied one survives untouched.
    assert set(data) == {"intro", "results", "conclusion"}
    assert data["results"]["prose"] == ""
    assert data["conclusion"]["prose"] == "Discussion prose.\n\nClosing remarks."

    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        assert set(cs.m5_writing["chapters"]) == {"intro", "results", "conclusion"}

    # …and the emptied chapter is still writable, which is the actual loss.
    r = client.patch(f"/api/v1/projects/{pid}/m5/chapters/results",
                     json={"prose": "Written again."})
    assert r.status_code == 200, r.text
    assert r.json()["prose"] == "Written again."


def test_get_chapters_normalization_keeps_a_non_canonical_key(client):
    # Same deletion, other shape: a key that is not one of the five at all
    # (`abstract`, and anything else a producer parked in `chapters`) is not
    # claimed by the merge either. Normalization folds RETIRED keys; it is not a
    # licence to prune everything it does not recognise.
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {"chapters": {
            "abstract": {"name": "abstract", "prose": "ABSTRACT", "pending_edits": []},
            "intro": {"name": "intro", "prose": "Intro prose.", "pending_edits": []},
            "discussion": {"name": "discussion", "prose": "Discussion prose.",
                           "pending_edits": []},
        }}
        flag_modified(cs, "m5_writing")
        db.commit()

    data = client.post(f"/api/v1/projects/{pid}/m5/chapters").json()
    assert set(data) == {"abstract", "intro", "conclusion"}
    assert data["abstract"]["prose"] == "ABSTRACT"
    assert data["conclusion"]["prose"] == "Discussion prose."

    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        stored = cs.m5_writing["chapters"]
        assert set(stored) == {"abstract", "intro", "conclusion"}
        assert stored["abstract"]["prose"] == "ABSTRACT"


def test_get_chapters_leaves_an_already_canonical_dict_untouched(client):
    # Normalization must not rewrite (or re-commit) the common case.
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    data = client.post(f"/api/v1/projects/{pid}/m5/chapters").json()
    assert set(data) == {"intro", "lit_review"}
    assert data["intro"]["prose"] == "Hello world."


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


def test_patch_chapter_blocks_hard_coherence_finding_before_commit(client, monkeypatch):
    """Editor saves use the M5 coherence boundary, not raw JSONB assignment."""
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    monkeypatch.setattr(
        "agent.coherence.validate_m5_sections",
        lambda *args: {"hard": 1, "crashed": False, "findings": [
            {"severity": "hard", "check": "coherence.number_mismatch"},
        ], "findings_hard": [{"severity": "hard", "check": "coherence.number_mismatch"}]},
    )
    r = client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "This must not persist."},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "coherence_violation"
    assert r.json()["detail"]["error"]["findings"] == [{"severity": "hard", "check": "coherence.number_mismatch"}]

    sf = get_session_factory()
    with sf() as db:
        assert db.get(ContextStore, uuid.UUID(pid)).m5_writing["chapters"]["intro"]["prose"] == "Hello world."


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


def test_get_references_reads_canonical_literature_sources(client):
    """Editor must show the same canonical M2 sources counted by the roadmap."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    assert r.status_code == 200
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {
            "literature_sources": [
                {"authors": ["Cohen", "Prayag", "Moıtal"], "year": "2013", "title": "Tourism behavior"},
                {"authors": ["Leung", "Law"], "year": "2013", "title": "Social media in tourism"},
            ],
            # This mirrors the reported project: canonical sources exist, while
            # gaps do not duplicate them as supporting_papers.
            "research_gaps": [],
        }
        flag_modified(cs, "m2_literature")
        db.commit()

    r = client.post(f"/api/v1/projects/{pid}/m5/references")
    assert r.status_code == 200
    refs = r.json()
    assert [(ref["author"], ref["year"]) for ref in refs] == [
        ("Cohen et al.", "2013"),
        ("Leung et al.", "2013"),
    ]
    assert all(ref.get("id") for ref in refs)


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


def test_editor_reference_search_merges_dedupes_and_ranks(client, monkeypatch):
    """Find papers combines both indexes but returns one DOI-deduped row."""
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    shared = {
        "title": "Influencer marketing and tourist intention",
        "authors": ["Nguyen", "Tran"], "year": 2024,
        "doi": "10.1234/tourism.1", "url": "https://doi.org/10.1234/tourism.1",
        "journal": "Tourism Review", "abstract": "Influencer credibility predicts tourist intention.",
        "citation_count": 42,
    }
    monkeypatch.setattr(
        "engine.utils.api_citations.openalex.OpenAlexClient.search_papers",
        lambda self, query, limit=10: [shared],
    )
    monkeypatch.setattr(
        "engine.utils.api_citations.semantic_scholar.SemanticScholarClient.search_papers",
        lambda self, query, limit=10: [{**shared, "citation_count": 50}],
    )
    monkeypatch.setattr(
        "app.routers.m5_editor._crossref_paper_search",
        lambda query, limit: [shared],
    )
    r = client.post(
        f"/api/v1/projects/{pid}/m5/references/search",
        json={"query": "influencer credibility tourist intention", "limit": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["results"][0]["doi"] == "10.1234/tourism.1"
    assert set(body["providers"]) == {"OpenAlex", "Semantic Scholar", "Crossref"}
    assert body["results"][0]["abstract_preview"]
    assert body["results"][0]["verified"] is False
    assert body["results"][0]["doi_available"] is True


def test_editor_add_reference_verifies_and_commits_to_m2(client, monkeypatch):
    """A chosen paper enters the canonical M2 slice through commit_slice."""
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    verified = {
        "id": "provider-owned-id",
        "title": "Influencer marketing and tourist intention",
        "authors": ["Nguyen", "Tran"], "year": 2024,
        "doi": "10.1234/tourism.1", "url": "https://doi.org/10.1234/tourism.1",
        "journal": "Tourism Review", "abstract": "Verified abstract.",
    }
    monkeypatch.setattr(
        "engine.utils.api_citations.openalex.OpenAlexClient.get_paper_by_doi",
        lambda self, doi: verified,
    )
    r = client.post(
        f"/api/v1/projects/{pid}/m5/references/add",
        json={"doi": "10.1234/tourism.1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["verified"] is True
    assert r.json()["id"] != "provider-owned-id"

    sf = get_session_factory()
    with sf() as db:
        sources = (db.get(ContextStore, uuid.UUID(pid)).m2_literature or {}).get("literature_sources")
        assert len(sources) == 1
        assert sources[0]["doi"] == "10.1234/tourism.1"


def test_editor_add_reference_rejects_different_resolved_doi(client, monkeypatch):
    """A DOI lookup must verify the selected DOI, not a plausible near match."""
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    monkeypatch.setattr(
        "engine.utils.api_citations.openalex.OpenAlexClient.get_paper_by_doi",
        lambda self, doi: {"title": "Different paper", "doi": "10.9999/different"},
    )
    r = client.post(
        f"/api/v1/projects/{pid}/m5/references/add",
        json={"doi": "10.1234/requested"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "reference_not_verified"


def test_editor_add_reference_does_not_claim_success_when_commit_rejects(client, monkeypatch):
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    monkeypatch.setattr(
        "engine.utils.api_citations.openalex.OpenAlexClient.get_paper_by_doi",
        lambda self, doi: {"title": "Verified", "doi": doi, "authors": ["Smith"], "year": 2024},
    )
    monkeypatch.setattr(
        "app.agent_state.DbProjectStateStore.commit_slice",
        lambda *args, **kwargs: {"error": "database_rejected"},
    )
    r = client.post(
        f"/api/v1/projects/{pid}/m5/references/add",
        json={"doi": "10.1234/requested"},
    )
    assert r.status_code == 500
    assert r.json()["detail"]["error"]["code"] == "reference_add_failed"


def test_editor_reference_ids_distinguish_same_author_and_year(client):
    """Author/year is citation display metadata, never source identity."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {"literature_sources": [
            {"authors": ["Smith"], "year": 2024, "title": "Paper one", "doi": "10.1/one"},
            {"authors": ["Smith"], "year": 2024, "title": "Paper two", "doi": "10.1/two"},
        ]}
        flag_modified(cs, "m2_literature")
        db.commit()

    refs = client.post(f"/api/v1/projects/{pid}/m5/references").json()
    assert len(refs) == 2
    assert len({r["id"] for r in refs}) == 2
    assert all(not r["ambiguous"] for r in refs)


def test_editor_reference_ids_distinguish_same_title_different_editions(client):
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {"literature_sources": [
            {"authors": ["Cohen"], "year": 2007, "title": "Consumer Behaviour in Tourism"},
            {"authors": ["Cohen"], "year": 2016, "title": "Consumer Behaviour in Tourism"},
        ]}
        flag_modified(cs, "m2_literature")
        db.commit()
    refs = client.post(f"/api/v1/projects/{pid}/m5/references").json()
    assert len(refs) == 2
    assert len({r["id"] for r in refs}) == 2


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
        json={"from_offset": from_o, "to_offset": to_o, "prompt": "Emphasise the causal link."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == kind
    assert body["new_text"] == "the rewritten selection"
    assert body["old_text"] == target
    assert "Emphasise the causal link." in mock_llm.call_args.args[0]
    assert body["metadata"]["prompt"] == "Emphasise the causal link."

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


@pytest.mark.parametrize(
    ("kind", "extra"),
    [
        ("paraphrase", {}),
        ("proofread", {}),
        ("improve", {}),
        ("humanize", {}),
        ("expand", {}),
        ("shorten", {}),
        ("translate", {"target_lang": "en"}),
    ],
)
@patch("orchestrator.tools.m5_inline._call_llm")
def test_inline_ai_rejects_empty_selection_before_model_call(mock_llm, client, kind, extra):
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/{kind}",
        json={"from_offset": 3, "to_offset": 3, **extra},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "empty_selection"
    mock_llm.assert_not_called()


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


def test_cite_uses_current_m2_authors_not_anonymous(client):
    """Editor citations must use the same label as M5 validation/export."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {"literature_sources": [{
            "authors": ["Nguyen", "Tran"], "year": 2024,
            "title": "Current source", "doi": "10.1/current",
        }]}
        flag_modified(cs, "m2_literature")
        db.commit()

    ref_id = client.post(f"/api/v1/projects/{pid}/m5/references").json()[0]["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 5, "reference_id": ref_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["new_text"] == " (Nguyen et al., 2024)"
    assert r.json()["metadata"]["document_fingerprint"]


def test_cite_honors_document_fingerprint_precondition(client):
    """Stale client selection never creates a proposal; a matching one does."""
    import hashlib
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {"literature_sources": [{
            "authors": ["Smith"], "year": 2024, "title": "Source", "doi": "10.1/source",
        }]}
        flag_modified(cs, "m2_literature")
        db.commit()
    ref_id = client.post(f"/api/v1/projects/{pid}/m5/references").json()[0]["id"]
    stale = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 5, "reference_id": ref_id, "expected_document_fingerprint": "stale"},
    )
    assert stale.status_code == 409
    with sf() as db:
        assert db.get(ContextStore, uuid.UUID(pid)).m5_writing["chapters"]["intro"]["pending_edits"] == []

    current = hashlib.sha256(b"Hello world.").hexdigest()
    accepted = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 5, "reference_id": ref_id, "expected_document_fingerprint": current},
    )
    assert accepted.status_code == 200


def test_accept_citation_rejects_whole_document_change(client):
    """A zero-length citation insertion must not survive an unrelated edit."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {"literature_sources": [{
            "authors": ["Smith"], "year": 2024, "title": "Source", "doi": "10.1/source",
        }]}
        flag_modified(cs, "m2_literature")
        db.commit()
    ref_id = client.post(f"/api/v1/projects/{pid}/m5/references").json()[0]["id"]
    edit = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 5, "reference_id": ref_id},
    ).json()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing["chapters"]["intro"]["prose"] = "An unrelated edit."
        flag_modified(cs, "m5_writing")
        db.commit()

    r = client.post(f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit['id']}/accept")
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "stale_document"


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


def test_cite_rejects_ambiguous_legacy_reference_id(client):
    """Old author/year-only records are never resolved by arbitrary list order."""
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m2_literature = {"literature_sources": [
            {"author": "Smith", "year": 2024},
            {"author": "Smith", "year": 2024},
        ]}
        flag_modified(cs, "m2_literature")
        db.commit()
    ref = client.post(f"/api/v1/projects/{pid}/m5/references").json()[0]
    assert ref["ambiguous"] is True

    r = client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 0, "reference_id": ref["id"]},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "reference_ambiguous"


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
    """Create a project then seed ALL 5 chapters into context_store.m5_writing.

    Decision: export requires all 5 chapters (M5_CHAPTER_ORDER); this helper is
    separate from _make_project_with_chapters (which only seeds 2) so the
    incomplete-chapters 400 test can reuse _make_project_with_chapters without
    modification.
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
                "conclusion":  {"name": "conclusion",  "prose": "Conclusion prose.",     "pending_edits": []},
            }
        }
        flag_modified(cs, "m5_writing")
        db.commit()
    return pid


@patch("app.routers.m5_editor.run_export")
def test_export_runs_both_compilers_and_returns_artifacts(mock_run_export, client):
    """1. Mock run_export → [docx artifact, pdf artifact]
    2. Auth + create project + seed ALL 5 chapters
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
    # Five-chapter collapse: "discussion" is retired, its content lives in
    # "conclusion" (M5_CHAPTER_ORDER), so it no longer appears as missing.
    assert set(body["missing_chapters"]) == {"methodology", "results", "conclusion"}
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


def test_get_chapters_tops_up_a_partly_materialised_dict(client):
    """`if chapters: return it` skipped the backfill whenever the dict was
    non-empty.

    Chapters are composed per module as each one finishes and only some paths
    write the editor's dict, so a real project arrived holding
    intro/lit_review/conclusion in `chapters` with methodology and results only
    in `final_sections`. The outline greyed both out — two finished chapters,
    45k characters, invisible and uneditable — while the export path read
    `final_sections` and shipped them.
    """
    from sqlalchemy.orm.attributes import flag_modified

    _create_user_and_set_cookie(client)
    r = client.post("/api/v1/projects", json={"name": "X"})
    pid = r.json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = {
            "chapters": {"intro": {"prose": "Edited in the editor."}},
            "final_sections": [
                {"chapter_name": "intro", "prose": "Stale compose snapshot."},
                {"chapter_name": "methodology", "prose": "Methodology prose."},
                {"chapter_name": "results", "prose": "Results prose."},
            ],
        }
        flag_modified(cs, "m5_writing")
        db.commit()

    data = client.post(f"/api/v1/projects/{pid}/m5/chapters").json()

    assert set(data) == {"intro", "methodology", "results"}
    assert data["methodology"]["prose"] == "Methodology prose."
    # An entry already in `chapters` wins — the student may have edited it, and
    # final_sections is a snapshot from whenever it was last composed.
    assert data["intro"]["prose"] == "Edited in the editor."

    # Persisted, so the next open does not have to re-derive it.
    with sf() as db:
        stored = db.get(ContextStore, uuid.UUID(pid)).m5_writing["chapters"]
    assert set(stored) == {"intro", "methodology", "results"}


def test_the_editor_opens_the_same_thesis_the_exporter_renders(client):
    """The editor's backfill and `m5_writing.chapter_prose` must not merely
    happen to agree — this pins them together.

    They are the same rule written twice: existing `chapters` entries win, the
    `final_sections` snapshot fills the gaps. The backfill is the one place that
    HEALS (it commits what it resolves), which is why it stays hand-written; but
    if it ever drifts from the resolver, the student edits one thesis on screen
    and downloads another. That is the whole class of bug this pins shut.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from orchestrator.tools.m5_writing import chapter_prose

    _create_user_and_set_cookie(client)
    pid = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]

    slice_ = {
        "chapters": {"intro": {"prose": "Edited in the editor."},
                     "conclusion": {"prose": "Closing chapter, edited."}},
        "final_sections": [
            {"chapter_name": "intro", "prose": "Stale compose snapshot."},
            {"chapter_name": "methodology", "prose": "Methodology prose."},
            {"title": "References", "prose": "Nguyen, A. (2020)."},
        ],
    }
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m5_writing = dict(slice_)
        flag_modified(cs, "m5_writing")
        db.commit()

    opened = client.post(f"/api/v1/projects/{pid}/m5/chapters").json()
    resolved = chapter_prose(slice_)

    assert {name: body["prose"] for name, body in opened.items()} == resolved
    # And specifically: the editor is not showing the stale snapshot.
    assert resolved["intro"] == "Edited in the editor."


@patch("app.routers.m5_editor.run_export")
def test_export_records_rows_the_download_route_authorizes_against(mock_run_export, client):
    """Every file the editor's Re-export produced 404'd on click.

    The download route's source of truth moved from m5_writing.export_artifacts
    to the `exports` table; this endpoint kept writing only the former, so the
    artifact existed in S3, the button rendered, and /exports/{filename} said
    artifact_not_found. Same rows the auto-export hook and the agent's
    export_docx tool write, so the three cannot drift again.
    """
    from app.models import Export

    mock_run_export.return_value = [
        {"kind": "docx", "s3_key": "projects/P/exports/thesis-abc.docx",
         "size_bytes": 42, "download_url": "/d", "uri": ""},
        {"kind": "pdf", "s3_key": "projects/P/exports/thesis-abc.pdf",
         "size_bytes": 99, "download_url": "/p", "uri": ""},
    ]
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    assert client.post(f"/api/v1/projects/{pid}/m5/export").status_code == 200

    sf = get_session_factory()
    with sf() as db:
        rows = db.query(Export).filter(Export.project_id == uuid.UUID(pid)).all()
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"docx", "pdf"}
    # The download route looks the artifact up by s3_key, and derives the
    # filename from the URL — both have to match what run_export produced.
    assert by_kind["docx"].s3_key == "projects/P/exports/thesis-abc.docx"
    assert by_kind["docx"].filename == "thesis-abc.docx"
    assert by_kind["pdf"].size_bytes == 99


@patch("app.routers.m5_editor.run_export")
def test_export_passes_the_store_so_it_renders_the_same_document(mock_run_export, client):
    """The editor was exporting a visibly different thesis from the chat.

    `run_export(context_store=...)` is what builds the cover fields, weaves the
    verified result tables into Chapter 4 and adds the research-model figure to
    Chapter 3. The agent's export_docx passed it; this endpoint did not, so the
    same project produced two different documents depending on which button the
    student pressed.
    """
    mock_run_export.return_value = [
        {"kind": "docx", "s3_key": "projects/P/exports/a.docx", "size_bytes": 1,
         "download_url": "/d", "uri": ""},
        {"kind": "pdf", "s3_key": "projects/P/exports/a.pdf", "size_bytes": 1,
         "download_url": "/p", "uri": ""},
    ]
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)

    assert client.post(f"/api/v1/projects/{pid}/m5/export").status_code == 200

    store = mock_run_export.call_args.kwargs["context_store"]
    # The NESTED shape run_export reads — not the flat owned-keys view.
    assert "m1_topic" in store and "m5_writing" in store
    assert isinstance(store["m1_topic"], dict)


def test_editor_reference_search_reuses_normalized_provider_cache(client, monkeypatch, tmp_path):
    """A repeated query uses cached raw rows without calling any index again."""
    _create_user_and_set_cookie(client)
    pid = _make_project_with_chapters(client)
    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(tmp_path / "research-cache"))
    calls = {"openalex": 0, "semantic": 0, "crossref": 0}
    paper = {
        "title": "Cacheable tourism evidence", "authors": ["Nguyen"], "year": 2024,
        "doi": "10.1234/cacheable", "abstract": "Tourism evidence.", "citation_count": 1,
    }

    def openalex(self, query, limit=10):
        calls["openalex"] += 1
        return [paper]

    def semantic(self, query, limit=10):
        calls["semantic"] += 1
        return [paper]

    def crossref(query, limit):
        calls["crossref"] += 1
        return [paper]

    monkeypatch.setattr("engine.utils.api_citations.openalex.OpenAlexClient.search_papers", openalex)
    monkeypatch.setattr("engine.utils.api_citations.semantic_scholar.SemanticScholarClient.search_papers", semantic)
    monkeypatch.setattr("app.routers.m5_editor._crossref_paper_search", crossref)

    first = client.post(f"/api/v1/projects/{pid}/m5/references/search", json={"query": "  Tourism   Evidence ", "limit": 5})
    second = client.post(f"/api/v1/projects/{pid}/m5/references/search", json={"query": "tourism evidence", "limit": 5})

    assert first.status_code == second.status_code == 200
    assert first.json()["count"] == second.json()["count"] == 1
    assert calls == {"openalex": 1, "semantic": 1, "crossref": 1}

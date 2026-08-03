"""Stateless helper tools — routers/tools.py.

The assertions that matter here are about HONESTY, not plumbing. Both endpoints
report on things a student will act on: whether their writing looks machine-
generated, and whether a reference is real. Overstating either is worse than
returning nothing — one invites false confidence, the other invites deleting a
genuine source.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from tests.conftest import make_user

EVEN = ("This is a sentence of words here. This is a sentence of words here. "
        "This is a sentence of words here. This is a sentence of words here.")
VARIED = ("Short. " + "The committee, having reviewed the sampling frame in "
          "considerable detail across three separate sessions, concluded that "
          "the stratification was defensible. It was not. " * 2)


@pytest.fixture
def user():
    Session = get_session_factory()
    with Session() as s:
        u = make_user(s, email="w@e.com")
        s.commit(); s.refresh(u); s.expunge(u)
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


# --- writing rhythm ---------------------------------------------------------

def test_uniform_sentences_score_high(user):
    r = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": EVEN})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] and b["score"] > 0.6
    assert b["verdict"] == "very_even"


def test_varied_sentences_score_lower(user):
    even = _as(user).post("/api/v1/tools/writing-rhythm",
                          json={"access_token": "x", "text": EVEN}).json()
    varied = _as(user).post("/api/v1/tools/writing-rhythm",
                            json={"access_token": "x", "text": VARIED}).json()
    assert varied["score"] < even["score"]


def test_too_short_is_declined_not_guessed(user):
    """Three sentences is the floor. Scoring one sentence would be a number with
    nothing behind it, which is worse than saying no."""
    r = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": "One sentence."})
    assert r.json()["ok"] is False
    assert r.json()["verdict"] == "too_short"


def test_the_response_never_claims_to_be_a_detector(user):
    """detector.py calls this a WEAK signal that must not be read as a verdict.
    If wording here ever implies Turnitin/GPTZero agreement, that is a product
    honesty regression, not a copy tweak."""
    b = _as(user).post("/api/v1/tools/writing-rhythm",
                       json={"access_token": "x", "text": EVEN}).json()
    blob = " ".join(str(v) for v in b.values()).lower()
    for banned in ("turnitin", "gptzero", "detector will", "will be flagged",
                   "ai-generated", "plagiar"):
        assert banned not in blob, f"response implies detection: {banned!r}"
    assert "burstiness" in b["basis"]


# --- citation verification --------------------------------------------------

def test_a_real_doi_is_confirmed(user, monkeypatch):
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_doi", lambda doi: {
        "DOI": doi, "title": ["Attention Is All You Need"],
        "author": [{"family": "Vaswani", "given": "Ashish"}],
        "issued": {"date-parts": [[2017]]},
        "container-title": ["NeurIPS"], "URL": "https://doi.org/x"})
    r = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x",
                             "reference": "Vaswani et al. 10.5555/3295222.3295349"})
    b = r.json()
    assert b["found"] is True
    assert b["matched_by"] == "doi"
    assert b["year"] == 2017
    # An exact DOI hit carries no fuzzy-match caveat.
    assert b["warning"] is None


def test_a_text_match_is_flagged_as_fuzzy(user, monkeypatch):
    """CrossRef returns its best guess for ANY query, so a title hit is evidence,
    not proof. Flattening that into found=true would be the dangerous shortcut."""
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_text", lambda q: {
        "DOI": "10.1/x", "title": ["Something Vaguely Similar"],
        "author": [], "issued": {"date-parts": [[2020]]}})
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x",
                             "reference": "Some paper about widgets, 2020"}).json()
    assert b["found"] is True
    assert b["matched_by"] == "search"
    assert "Fuzzy" in b["warning"]


def test_a_missing_doi_does_not_call_it_fabricated(user, monkeypatch):
    """A typo looks identical to an invention here. The wording must not push a
    student into deleting a real source."""
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_doi", lambda doi: None)
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x", "reference": "10.9999/nope"}).json()
    assert b["found"] is False
    assert "typo" in b["detail"].lower()


def test_no_crossref_match_explains_the_limits_of_crossref(user, monkeypatch):
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_text", lambda q: None)
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x", "reference": "A book, 1998"}).json()
    assert b["found"] is False
    assert "not proof" in b["detail"].lower()


def test_a_network_failure_is_never_reported_as_not_found(user, monkeypatch):
    """The worst possible error: telling a student a real citation is fake
    because CrossRef was briefly unreachable."""
    import app.routers.tools as t

    def _boom(*a, **k):
        raise RuntimeError("connection reset")
    monkeypatch.setattr(t, "_crossref_by_text", _boom)
    b = _as(user).post("/api/v1/tools/verify-citation",
                       json={"access_token": "x", "reference": "Something, 2020"}).json()
    assert b["ok"] is False
    assert b["found"] is False
    assert "no conclusion" in b["detail"].lower()


# --- transport ---------------------------------------------------------------

@pytest.mark.parametrize("path,body", [
    ("/api/v1/tools/writing-rhythm", {"text": EVEN}),
    ("/api/v1/tools/verify-citation", {"reference": "10.1/x"}),
])
def test_header_only_auth_works(user, path, body, monkeypatch):
    """The MCP path: the token is an Authorization header and there is NO
    access_token in the body. An AuthedBody schema here makes Pydantic 422 the
    request before current_user ever reads the header — which is exactly how
    both of these shipped broken and were caught only against production.

    Every test above passes access_token in the body, so none of them covered
    the transport the connector actually uses.
    """
    import app.routers.tools as t
    monkeypatch.setattr(t, "_crossref_by_doi", lambda doi: None)

    client = _as(user)
    r = client.post(path, json=body, headers={"Authorization": "Bearer irrelevant"})
    assert r.status_code == 200, r.text

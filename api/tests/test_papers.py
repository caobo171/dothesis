import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def _signed_in_client():
    """Build an authenticated TestClient.

    Auth migration: signup no longer auto-issues a session (cookies are
    gone; tokens are stateless). Tests skip the signup→email-verify→login
    dance entirely and mint a JWT directly for a seed user — same outcome,
    no SES dependency. Without this, signup blew up trying to send the
    verify email through unconfigured SES in CI.
    """
    from app.db import get_session_factory
    from app.models import User
    from app.security import create_session, hash_password
    Session = get_session_factory()
    with Session() as db:
        u = User(email="u@x.com", username="tester",
                password_hash=hash_password("supersecret"),
                email_verified=True, credit=10000)
        db.add(u)
        db.commit()
        token = create_session(db, u)
    c = TestClient(create_app())
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def _brief():
    return {
        "topic": "Algorithmic decision making and democratic accountability",
        "research_question": "How do EU and US diverge?",
        "academic_level": "master",
        "language": "en",
        "model": "gemini-flash",
        "citation_style": "apa",
        "sources": {"crossref": True, "openalex": True, "semanticscholar": True,
                     "arxiv": True, "jstor": False, "googleScholar": False},
        "tone": "rigorous",
    }


def test_list_papers_empty():
    c = _signed_in_client()
    r = c.get("/api/v1/papers")
    assert r.status_code == 200
    assert r.json() == []


def test_create_paper_spawns_job():
    c = _signed_in_client()
    with patch("app.routers.papers.spawn_job") as spawn:
        r = c.post("/api/v1/papers", json=_brief())
    assert r.status_code == 201, r.text
    body = r.json()
    assert "paper_id" in body and "job_id" in body
    assert spawn.called


@pytest.mark.skip(reason="superseded by Plan 2 tier-based pricing; model field removed")
def test_create_paper_rejects_unknown_model():
    c = _signed_in_client()
    bad = {**_brief(), "model": "made-up"}
    r = c.post("/api/v1/papers", json=bad)
    assert r.status_code == 422


def test_create_paper_blocks_when_already_running():
    c = _signed_in_client()
    with patch("app.routers.papers.spawn_job"):
        c.post("/api/v1/papers", json=_brief())
    r = c.post("/api/v1/papers", json=_brief())
    assert r.status_code == 409


def test_list_paper_includes_created():
    c = _signed_in_client()
    with patch("app.routers.papers.spawn_job"):
        c.post("/api/v1/papers", json=_brief())
    r = c.get("/api/v1/papers")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["title"].startswith("Algorithmic")


def test_unauthenticated_returns_401():
    c = TestClient(create_app())
    assert c.get("/api/v1/papers").status_code == 401

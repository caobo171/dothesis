from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def _signed_in_client():
    c = TestClient(create_app())
    c.post("/api/v1/auth/signup", json={"email": "u@x.com", "password": "supersecret"})
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

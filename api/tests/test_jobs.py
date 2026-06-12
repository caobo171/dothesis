import json
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.main import create_app
from app.models import Job, JobEvent, Paper


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


def _seed_paper(c, brief):
    with patch("app.routers.papers.spawn_job"):
        r = c.post("/api/v1/papers", json=brief)
    return r.json()


def _brief():
    return {
        "topic": "x x x x", "research_question": "q",
        "academic_level": "master", "language": "en",
        "model": "gemini-flash", "citation_style": "apa",
        "sources": {"crossref": True, "openalex": True, "semanticscholar": True,
                     "arxiv": True, "jstor": False, "googleScholar": False},
        "tone": "rigorous",
    }


def test_get_job_returns_status():
    c = _signed_in_client()
    ids = _seed_paper(c, _brief())
    r = c.get(f"/api/v1/jobs/{ids['job_id']}")
    assert r.status_code == 200
    assert r.json()["status"] in {"queued", "running"}


def test_cannot_see_other_users_job():
    c1 = _signed_in_client()
    ids = _seed_paper(c1, _brief())
    c2 = TestClient(create_app())
    c2.post("/api/v1/auth/signup", json={"email": "v@x.com", "password": "supersecret"})
    r = c2.get(f"/api/v1/jobs/{ids['job_id']}")
    assert r.status_code == 404


def test_sse_replays_backlog():
    c = _signed_in_client()
    ids = _seed_paper(c, _brief())
    job_id = uuid.UUID(ids["job_id"])

    with OrmSession(get_engine()) as db:
        db.add(JobEvent(job_id=job_id, type="activity", phase="research", agent="Scout", text="hi"))
        db.add(JobEvent(job_id=job_id, type="job_done"))
        db.commit()

    with c.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        body = b""
        for chunk in resp.iter_bytes():
            body += chunk
            if b"job_done" in body:
                break
    text = body.decode()
    assert "activity" in text
    assert "job_done" in text

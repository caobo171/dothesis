import json
import uuid
from unittest.mock import patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.main import create_app
from app.models import Job, Paper
from app.settings import get_settings


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


def _seed_done_paper(client):
    brief = {
        "topic": "topic", "research_question": "q",
        "academic_level": "master", "language": "en",
        "model": "gemini-flash", "citation_style": "apa",
        "sources": {"crossref": True, "openalex": True, "semanticscholar": True,
                     "arxiv": True, "jstor": False, "googleScholar": False},
        "tone": "rigorous",
    }
    with patch("app.routers.papers.spawn_job"):
        ids = client.post("/api/v1/papers", json=brief).json()
    with OrmSession(get_engine()) as db:
        job = db.get(Job, uuid.UUID(ids["job_id"]))
        paper = db.get(Paper, uuid.UUID(ids["paper_id"]))
        job.status = "done"
        paper.status = "done"
        db.commit()
        # expire_on_commit defaults to True, so commit expires every attribute;
        # touch the fields callers read (paper.id/user_id, job.id) while the
        # session is still open so they're loaded before the instance detaches.
        # Otherwise _put() lazy-loads them post-close → DetachedInstanceError.
        _ = (paper.id, paper.user_id, job.id)
        return paper, job


@pytest.fixture
def _s3():
    settings = get_settings()
    with mock_aws():
        c = boto3.client("s3", region_name=settings.aws_region,
                          aws_access_key_id=settings.aws_access_key,
                          aws_secret_access_key=settings.aws_secret_key)
        c.create_bucket(Bucket=settings.s3_bucket,
                         CreateBucketConfiguration={"LocationConstraint": settings.aws_region})
        yield c


def _put(s3, paper, job, rel, body, ct):
    settings = get_settings()
    key = f"{settings.s3_prefix}users/{paper.user_id}/papers/{paper.id}/jobs/{job.id}/{rel}"
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=body, ContentType=ct)


def test_draft_returns_markdown_and_chapters(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    _put(_s3, p, j, "exports/draft.md", b"# Title\n\n## Introduction\n\nhi\n\n## Methods\n\nok\n", "text/markdown")
    # draft route migrated GET->POST (post-only endpoints).
    r = c.post(f"/api/v1/papers/{p.id}/draft")
    assert r.status_code == 200
    data = r.json()
    assert "Introduction" in data["markdown"]
    assert [ch["title"] for ch in data["chapters"]] == ["Introduction", "Methods"]


def test_citations_returns_list(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    bib = [{"key": "k1", "title": "Paper One", "authors": ["A. Doe"], "year": 2024,
             "doi": "10.1/x", "source": "CrossRef", "venue": "Journal"}]
    _put(_s3, p, j, "research/bibliography.json", json.dumps(bib).encode(), "application/json")
    # citations route migrated GET->POST (post-only endpoints).
    r = c.post(f"/api/v1/papers/{p.id}/citations")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Paper One"


def test_exports_lists_only_present_formats(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    _put(_s3, p, j, "exports/draft.pdf", b"%PDF-1.4 fake", "application/pdf")
    # exports list route migrated GET->POST (post-only endpoints).
    r = c.post(f"/api/v1/papers/{p.id}/exports")
    assert r.status_code == 200
    formats = [e["format"] for e in r.json()]
    assert formats == ["pdf"]


def test_download_returns_302(_s3):
    c = _signed_in_client()
    p, j = _seed_done_paper(c)
    _put(_s3, p, j, "exports/draft.pdf", b"%PDF-1.4 fake", "application/pdf")
    # Download stays GET but the JWT is no longer accepted in the URL; mint a
    # short-lived scoped stream token and pass it via ?st= (post-only endpoints).
    token = c.headers["Authorization"].split(" ", 1)[1]
    st = c.post("/api/v1/auth/stream-token",
                json={"access_token": token, "scope": f"paper-export:{p.id}:pdf"}).json()["stream_token"]
    r = c.get(f"/api/v1/papers/{p.id}/exports/pdf?st={st}", follow_redirects=False)
    assert r.status_code == 302
    assert "draft.pdf" in r.headers["location"]

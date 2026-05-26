"""Upload a PDF, then verify M2 seed includes the upload's URI."""
import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import create_session


pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[3] / "api" / "tests" / "fixtures" / "sample.pdf"


class _FakeS3:
    """In-memory stand-in for boto3 S3 client.

    Uses an instance-level dict so each test gets isolated storage (avoids
    cross-test state leakage that would occur with a class-level attribute).
    """
    def __init__(self):
        self._store: dict = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        data = Body if isinstance(Body, bytes) else Body.encode()
        self._store[f"{Bucket}/{Key}"] = data

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self._store[f"{Bucket}/{Key}"])}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    fake_s3 = _FakeS3()
    monkeypatch.setattr("app.routers.uploads.s3_from_env", lambda: fake_s3)
    return TestClient(create_app())


def _login(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("opendraft_session", create_session(db, u))
        return u.id


def test_upload_then_m2_seed_includes_paper_uris(client, monkeypatch):
    _login(client)
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]

    with FIXTURE.open("rb") as f:
        r = client.post(
            f"/api/v1/projects/{pid}/uploads",
            files={"file": ("smith2024.pdf", f, "application/pdf")},
        )
    assert r.status_code == 200

    from orchestrator.agents.m2.translation import _seed_from_outer
    from orchestrator.state import ContextStore

    outer_state = {
        "project_id": uuid.UUID(pid),
        "thread_id": uuid.uuid4(),
        "messages": [],
        "current_module": "M2",
        "context_store": ContextStore(
            m1_topic={"research_title": "X", "research_type": "quantitative",
                      "language": "en", "confirmed_at": "2026-05-26"},
        ),
        "mode": "auto",
    }
    sf = get_session_factory()
    with sf() as db:
        sub = _seed_from_outer(outer_state, db)
    assert len(sub["paper_uris"]) == 1
    assert sub["paper_uris"][0].endswith("smith2024.pdf")

"""Tests for POST /projects/{id}/threads/start-at/{artifact} (Phase 5 / E3)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Thread, User


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _auth_and_project(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        from app.security import create_session
        token = create_session(db, u)
    client.headers["Authorization"] = f"Bearer {token}"
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    return uuid.UUID(pid)


def test_start_at_creates_thread_with_target(client):
    pid = _auth_and_project(client)
    r = client.post(f"/api/v1/projects/{pid}/threads/start-at/analysis")
    assert r.status_code == 200
    tid = uuid.UUID(r.json()["id"])
    sf = get_session_factory()
    with sf() as db:
        t = db.get(Thread, tid)
        assert t.target_artifact == "analysis"


def test_start_at_rejects_unknown_artifact(client):
    pid = _auth_and_project(client)
    r = client.post(f"/api/v1/projects/{pid}/threads/start-at/bogus")
    assert r.status_code == 422

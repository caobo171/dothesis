"""Tests for GET /projects/{pid}/runs?latest=true."""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Job, Project, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _login_and_project(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("opendraft_session", create_session(db, u))
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_latest_returns_null_when_no_runs(client):
    pid = _login_and_project(client)
    r = client.get(f"/api/v1/projects/{pid}/runs?latest=true")
    assert r.status_code == 200
    assert r.json() == {"run": None}


def test_latest_returns_most_recent_run(client):
    pid = _login_and_project(client)
    sf = get_session_factory()
    from datetime import datetime, timezone, timedelta
    with sf() as db:
        older = Job(project_id=pid, mode="auto", status="done",
                    started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        db.add(older); db.flush()
        newer = Job(project_id=pid, mode="auto", status="running",
                    started_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        db.add(newer); db.commit()
        newer_id = newer.id

    r = client.get(f"/api/v1/projects/{pid}/runs?latest=true")
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["id"] == str(newer_id)
    assert body["run"]["status"] == "running"

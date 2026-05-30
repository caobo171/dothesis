"""Tests for the artifact readiness + import endpoints (Phase 2)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, User

_FULL_TOPIC = {
    "research_title": "X", "field": "Marketing", "research_type": "quantitative",
    "target_population": "Gen Z", "scope": "National",
    "objectives": ["o1"], "research_questions": ["q1"],
}


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
    client.cookies.set("opendraft_session", token)
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    return uuid.UUID(pid)


def _seed_slice(pid, **slices):
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, pid)
        for k, v in slices.items():
            setattr(cs, k, v)
        db.add(cs); db.commit()


def test_artifacts_endpoint_empty_project_topic_ready(client):
    pid = _auth_and_project(client)
    r = client.get(f"/api/v1/projects/{pid}/artifacts")
    assert r.status_code == 200
    body = r.json()
    assert body["topic"] == "ready"
    assert body["literature"] == "blocked"


def test_artifacts_endpoint_reflects_seeded_topic(client):
    pid = _auth_and_project(client)
    _seed_slice(pid, m1_topic=_FULL_TOPIC)
    body = client.get(f"/api/v1/projects/{pid}/artifacts").json()
    assert body["topic"] == "done"
    assert body["literature"] == "ready"

"""Tests for GET /threads/{tid}/state SSE endpoint."""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, Project, Thread, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup(client) -> tuple[uuid.UUID, uuid.UUID]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("opendraft_session", create_session(db, u))
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.get(f"/api/v1/projects/{pid}/threads").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def test_state_stream_emits_initial_snapshot(client):
    pid, tid = _setup(client)
    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, pid)
        cs.m1_topic = {"research_title": "X", "confirmed_at": "2026-05-26"}
        db.commit()

    with client.stream("GET", f"/api/v1/threads/{tid}/state") as r:
        assert r.status_code == 200
        chunks = []
        for line in r.iter_lines():
            chunks.append(line)
            if len(chunks) > 5:
                break

    body = "\n".join(c for c in chunks if c)
    assert "data:" in body
    assert "context_update" in body

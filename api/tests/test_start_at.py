"""Tests for POST /projects/{id}/threads/start-at/{artifact} (Phase 5 / E3)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

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
    client.cookies.set("opendraft_session", token)
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


def test_send_message_seeds_target_artifact_on_first_turn(client, monkeypatch):
    pid = _auth_and_project(client)
    tid = client.post(f"/api/v1/projects/{pid}/threads/start-at/analysis").json()["id"]

    captured = {}

    def fake_astream(graph_input, **kwargs):
        captured["input"] = graph_input

        async def _it():
            from langchain_core.messages import AIMessage
            yield {"M1": {"messages": [AIMessage(content="ok")]}}
        return _it()

    fake_graph = MagicMock()
    fake_graph.astream = fake_astream
    fake_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    monkeypatch.setattr("orchestrator.graph.get_interactive_graph", lambda: fake_graph)

    client.post(f"/api/v1/threads/{tid}/messages", json={"text": "hi"})
    assert captured["input"].get("target_artifact") == "analysis"

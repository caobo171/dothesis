"""DOTHESIS_AGENT_V3 — the deep-agent turn behind the same SSE contract."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Message, User


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setenv("DOTHESIS_AGENT_V3", "1")
    return TestClient(create_app())


def _setup_project(client) -> tuple[uuid.UUID, uuid.UUID]:
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
    # GET→POST migration: list route renamed to /threads/list (POST).
    tid = client.post(f"/api/v1/projects/{pid}/threads/list").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def test_v3_turn_streams_and_persists(client, monkeypatch):
    pid, tid = _setup_project(client)

    # Stub the agent layer: a fixed event stream instead of a model call.
    # The contract under test is chat_v3's bridging — SSE shapes + Message
    # persistence — not deepagents itself.
    async def fake_stream_turn(agent, thread_id, text, attachments=None):
        for ev in [
            {"type": "tool_start", "name": "read_slice", "args": {"module": "M1"}},
            {"type": "tool_end", "name": "read_slice", "preview": "{}"},
            {"type": "token", "text": "Xin chào! "},
            {"type": "token", "text": "Bạn đã có gì cho luận văn?"},
            {"type": "done"},
        ]:
            yield ev

    async def fake_get_agent(db, project_id):
        return object()

    monkeypatch.setattr("app.routers.chat_v3._get_agent", fake_get_agent)
    monkeypatch.setattr("agent.runtime.stream_turn", fake_stream_turn)

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "hello"})
    assert resp.status_code == 200
    body = resp.text
    # Tool activity rides the existing progress event the web renders live.
    assert '"type": "progress"' in body
    assert "read_slice" in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body

    sf = get_session_factory()
    with sf() as db:
        msgs = db.query(Message).filter_by(thread_id=tid).order_by(Message.id).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == "Xin chào! Bạn đã có gì cho luận văn?"


def test_v3_error_event_surfaces(client, monkeypatch):
    pid, tid = _setup_project(client)

    async def fake_stream_turn(agent, thread_id, text, attachments=None):
        yield {"type": "error", "message": "BoomError: model exploded"}
        yield {"type": "done"}

    async def fake_get_agent(db, project_id):
        return object()

    monkeypatch.setattr("app.routers.chat_v3._get_agent", fake_get_agent)
    monkeypatch.setattr("agent.runtime.stream_turn", fake_stream_turn)

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "hi"})
    assert '"type": "error"' in resp.text
    assert "BoomError" in resp.text

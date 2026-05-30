"""Tests for the SSE message streaming endpoint."""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Message, User


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup_project(client) -> tuple[uuid.UUID, uuid.UUID]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        from app.security import create_session
        # create_session returns a signed cookie value; use the correct
        # cookie name expected by deps.py (opendraft_session).
        token = create_session(db, u)
    client.cookies.set("opendraft_session", token)
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.get(f"/api/v1/projects/{pid}/threads").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def _async_iter(items):
    async def _it():
        for it in items:
            yield it
    return _it()


def test_send_message_persists_user_msg_and_streams_reply(client, monkeypatch):
    pid, tid = _setup_project(client)
    from langchain_core.messages import AIMessage

    fake_graph = MagicMock()
    fake_graph.astream.return_value = _async_iter([
        {"M1": {"messages": [AIMessage(content="Hello! What's your topic?")]}},
    ])
    # send_message awaits graph.aget_state(...) for first-turn detection + the
    # post-run context_store sync, so it must be an async mock. (values={} → the
    # turn is treated as first-turn and the DB sync is a no-op.)
    fake_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(
        f"/api/v1/threads/{tid}/messages",
        json={"text": "leadership thesis"},
    )
    assert resp.status_code == 200
    assert "Hello" in resp.text

    sf = get_session_factory()
    with sf() as db:
        msgs = db.query(Message).filter_by(thread_id=tid).order_by(Message.id).all()
        assert msgs[0].role == "user"
        assert msgs[0].content == "leadership thesis"
        assert msgs[-1].role == "assistant"
        assert "Hello" in msgs[-1].content

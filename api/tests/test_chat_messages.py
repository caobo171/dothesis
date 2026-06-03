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


def test_send_message_passes_thread_id_into_graph_input(client, monkeypatch):
    """Regression guard: chat.py MUST write `thread_id` into the graph input
    on every turn. M2's deep-research progress emitter is registered under
    `langgraph_thread_id` in engine.utils.progress and looked up by M2Agent
    via `state.get("thread_id")`. Without this write the lookup returns
    None, the emitter is never called, and the M2 search-progress beats
    never reach the SSE queue — the chat bubble stays stuck on '...' for
    the entire (potentially multi-minute) search run.

    Bug originally landed in commit 14e75f5 ('move emitter out of graph
    state') which switched the lookup site to state.get('thread_id') but
    forgot to populate the field at the chat front door. This test pins
    the contract so the wire can't silently rot again.
    """
    from langchain_core.messages import AIMessage

    captured: dict = {}

    fake_graph = MagicMock()

    def _record(graph_input, **kwargs):
        captured["graph_input"] = graph_input
        return _async_iter([
            {"M1": {"messages": [AIMessage(content="hi")]}},
        ])
    fake_graph.astream.side_effect = _record
    fake_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    pid, tid = _setup_project(client)
    resp = client.post(
        f"/api/v1/threads/{tid}/messages", json={"text": "go"},
    )
    assert resp.status_code == 200

    assert "thread_id" in captured["graph_input"], (
        "graph_input is missing 'thread_id' — M2 progress emitter lookup "
        "will return None and search-progress beats will not reach SSE."
    )
    # Must match the value used at register() time so the lookup hits.
    sf = get_session_factory()
    with sf() as db:
        from app.models import Thread
        t = db.query(Thread).filter_by(id=tid).one()
        assert captured["graph_input"]["thread_id"] == t.langgraph_thread_id

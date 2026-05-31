"""Tests that the chat message endpoint emits tool_calls SSE events
and persists the payload to messages.tool_calls_json."""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Message, User
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


def _async_iter(items):
    async def _it():
        for x in items:
            yield x
    return _it()


# aget_state is awaited in the router; default MagicMock returns a non-
# awaitable, breaking the call. Each test that fakes the graph uses this
# helper to stub aget_state with a coroutine returning an empty-state
# object (so the router treats it as the first turn).
class _NullState:
    values = None


def _attach_aget_state_stub(fake_graph):
    async def _aget_state(_config):
        return _NullState()
    fake_graph.aget_state = _aget_state
    return fake_graph


def test_stream_emits_tool_calls_event_and_persists(client, monkeypatch):
    pid, tid = _setup(client)

    # Stub the interactive graph to emit ONE update with an assistant message
    # carrying tool_calls_json in additional_kwargs, then 'done'.
    from langchain_core.messages import AIMessage
    ai = AIMessage(content="Pick a field")
    ai.additional_kwargs["tool_calls_json"] = {
        "widget_type": "card_grid", "field_name": "field",
        "title": "Pick", "options": [], "columns": 3,
    }

    fake_graph = _attach_aget_state_stub(MagicMock())
    fake_graph.astream.return_value = _async_iter([
        {"M1": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(
        f"/api/v1/threads/{tid}/messages",
        json={"text": "hi"},
    )
    assert resp.status_code == 200
    body = resp.text
    # SSE body contains a tool_calls event with the payload
    assert '"type": "tool_calls"' in body or '"type":"tool_calls"' in body
    assert "card_grid" in body

    # Persisted Message row carries the JSONB payload
    sf = get_session_factory()
    with sf() as db:
        assistants = db.query(Message).filter_by(thread_id=tid, role="assistant").all()
        assert assistants, "expected assistant Message row"
        assert assistants[-1].tool_calls_json is not None
        assert assistants[-1].tool_calls_json["widget_type"] == "card_grid"
        assert assistants[-1].tool_calls_json["field_name"] == "field"


def test_stream_forwards_engine_progress_events(client, monkeypatch):
    """P3: when M2 phase2 binds the chat router's emitter, every safe_print
    line fires as a structured progress event. The chat router must
    multiplex those alongside the graph node updates and surface them as
    SSE `type: progress` lines so the frontend can show a live banner
    instead of a 30-60s typing dot."""
    pid, tid = _setup(client)
    from langchain_core.messages import AIMessage

    async def fake_astream(graph_input, config=None, stream_mode=None):
        # Simulate the engine emitting two progress lines BEFORE the node's
        # final message returns. The chat router should forward these
        # progress events to the SSE stream.
        emitter = graph_input.get("_progress_emitter")
        assert emitter is not None, "chat router must forward emitter"
        emitter({"stage": "scout.start",
                 "message": "🔍 Searching for citations on \"Gen Z\"…"})
        emitter({"stage": "scout.api_chain",
                 "message": "🔀 API chain: gemini_grounded → crossref"})
        # Tiny yield so the loop has a chance to schedule the queued events
        # before the final node update lands in the same queue.
        import asyncio as _aio
        await _aio.sleep(0)
        yield {"M2": {"messages": [AIMessage(content="Synthesis ready.")]}}

    fake_graph = _attach_aget_state_stub(MagicMock())
    fake_graph.astream = fake_astream
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph)

    resp = client.post(
        f"/api/v1/threads/{tid}/messages",
        json={"text": "do citations"},
    )
    assert resp.status_code == 200
    body = resp.text
    # Both progress events surface; the final token still goes through.
    assert '"type": "progress"' in body or '"type":"progress"' in body
    assert "Searching for citations" in body
    assert "API chain" in body
    assert "Synthesis ready" in body


def test_list_messages_returns_tool_calls_json(client, monkeypatch):
    """GET /threads/{id}/messages must include tool_calls_json so the frontend
    can hydrate widget bubbles on page load."""
    pid, tid = _setup(client)

    sf = get_session_factory()
    with sf() as db:
        db.add(Message(
            thread_id=tid, role="assistant", content="Pick",
            module_tag="M1",
            tool_calls_json={"widget_type": "card_grid",
                             "field_name": "field",
                             "title": "Pick",
                             "options": [{"value": "x", "label": "X"}],
                             "columns": 3},
        ))
        db.commit()

    r = client.get(f"/api/v1/threads/{tid}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert msgs, "expected at least one message"
    last = msgs[-1]
    assert last["tool_calls_json"] is not None
    assert last["tool_calls_json"]["widget_type"] == "card_grid"


def test_stream_emits_list_editor_tool_calls_event(client, monkeypatch):
    """The chat router already forwards any additional_kwargs['tool_calls_json']
    as an SSE 'tool_calls' event (added in SP3). This test verifies the existing
    code path handles the new list_editor variant — no router changes needed."""
    pid, tid = _setup(client)

    from langchain_core.messages import AIMessage
    ai = AIMessage(content="Pick themes")
    ai.additional_kwargs["tool_calls_json"] = {
        "widget_type": "list_editor",
        "field_name": "themes",
        "title": "Pick themes",
        "initial_items": [
            {"id": "t1", "text": "Theme 1", "sub_items": []},
            {"id": "t2", "text": "Theme 2", "sub_items": []},
        ],
        "allow_nested": True,
        "confirm_label": "Confirm", "reset_label": "Reset to suggested",
    }

    fake_graph = _attach_aget_state_stub(MagicMock())
    fake_graph.astream.return_value = _async_iter([
        {"M3": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "go"})
    assert resp.status_code == 200
    body = resp.text
    assert '"type": "tool_calls"' in body or '"type":"tool_calls"' in body
    assert "list_editor" in body
    assert "Theme 1" in body

    sf = get_session_factory()
    with sf() as db:
        assistants = db.query(Message).filter_by(thread_id=tid, role="assistant").all()
        assert assistants
        assert assistants[-1].tool_calls_json["widget_type"] == "list_editor"
        assert assistants[-1].tool_calls_json["field_name"] == "themes"


def test_stream_emits_analysis_outline_tool_calls_event(client, monkeypatch):
    """SP5 contract test — the SP3 router forwards analysis_outline list_editor
    payloads through the SSE stream and persistence path. No router changes."""
    pid, tid = _setup(client)

    from langchain_core.messages import AIMessage
    ai = AIMessage(content="Pick your outline")
    ai.additional_kwargs["tool_calls_json"] = {
        "widget_type": "list_editor",
        "field_name": "analysis_outline",
        "title": "SPSS analysis outline",
        "initial_items": [
            {"id": "s0", "text": "Descriptive Statistics", "sub_items": [], "meta": {"thresholds": ""}},
            {"id": "s1", "text": "Reliability (Cronbach's Alpha)", "sub_items": [],
             "meta": {"thresholds": "α ≥ 0.7"}},
        ],
        "allow_nested": False,
        "confirm_label": "Confirm", "reset_label": "Reset to suggested",
    }

    fake_graph = _attach_aget_state_stub(MagicMock())
    fake_graph.astream.return_value = _async_iter([
        {"M4": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "go"})
    assert resp.status_code == 200
    body = resp.text
    assert '"type": "tool_calls"' in body or '"type":"tool_calls"' in body
    assert "list_editor" in body
    assert "analysis_outline" in body
    assert "Reliability" in body

    sf = get_session_factory()
    with sf() as db:
        assistants = db.query(Message).filter_by(thread_id=tid, role="assistant").all()
        assert assistants
        assert assistants[-1].tool_calls_json["field_name"] == "analysis_outline"

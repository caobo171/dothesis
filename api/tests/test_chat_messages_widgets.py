"""GET /threads/{id}/messages/list returns tool_calls_json so the frontend
can hydrate widget bubbles on page load.

(The v2 streaming-emit tests that mocked orchestrator.graph were removed with
the v2 interactive turn path — v3 is the only chat brain now.)"""
import uuid

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
        client.headers["Authorization"] = f"Bearer {create_session(db, u)}"
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    # GET→POST migration: list route renamed to /threads/list (POST).
    tid = client.post(f"/api/v1/projects/{pid}/threads/list").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


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

    # GET→POST migration: list route renamed to /messages/list (POST);
    # pagination params (before_id, limit) move into the JSON body.
    r = client.post(f"/api/v1/threads/{tid}/messages/list", json={})
    assert r.status_code == 200
    msgs = r.json()
    assert msgs, "expected at least one message"
    last = msgs[-1]
    assert last["tool_calls_json"] is not None
    assert last["tool_calls_json"]["widget_type"] == "card_grid"

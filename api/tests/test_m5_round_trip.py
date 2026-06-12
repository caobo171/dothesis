"""Contract test: M5 rewrite-keyword user messages persist correctly and the
agent's next step() can detect them. No router or graph changes required."""
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
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")
    return TestClient(create_app())


def _async_iter(items):
    async def _it():
        for x in items:
            yield x
    return _it()


def test_rewrite_request_persists_to_message_row(client, monkeypatch):
    """User sends 'rewrite chapter 3' → the chat router persists it as a user
    Message. Next agent step() would route to _handle_rewrite. No router code
    needs to change for SP6 — this test documents the contract."""
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.headers["Authorization"] = f"Bearer {create_session(db, u)}"
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.get(f"/api/v1/projects/{pid}/threads").json()[0]["id"]

    from langchain_core.messages import AIMessage
    ai = AIMessage(content="acknowledged")
    fake_graph = MagicMock()
    fake_graph.astream.return_value = _async_iter([
        {"M5": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph,
    )

    resp = client.post(
        f"/api/v1/threads/{tid}/messages",
        json={"text": "rewrite chapter 3 to be less formal"},
    )
    assert resp.status_code == 200

    sf = get_session_factory()
    with sf() as db:
        users_msgs = (
            db.query(Message)
              .filter_by(thread_id=tid, role="user")
              .order_by(Message.id)
              .all()
        )
        assert any("rewrite chapter 3" in m.content.lower() for m in users_msgs)

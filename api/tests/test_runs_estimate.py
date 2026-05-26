"""Tests for GET /projects/{pid}/runs/estimate?topic=..."""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True, credit=10000)
        db.add(u); db.commit()
        client.cookies.set("opendraft_session", create_session(db, u))
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_estimate_returns_token_and_credit_info(client):
    pid = _setup(client)
    r = client.get(f"/api/v1/projects/{pid}/runs/estimate?topic=Leadership in SMEs")
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_tokens"] > 0
    assert "credit_balance" in body
    assert body["credit_balance"] == 10000

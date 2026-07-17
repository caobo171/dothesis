"""GET /projects/{id}/gate-summary — committee-readiness B2B route (roadmap #12)."""
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
    return TestClient(create_app(), follow_redirects=False)


def _user_and_project(client):
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit(); db.refresh(u)
        token = create_session(db, u)
    client.headers["Authorization"] = f"Bearer {token}"
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    return pid


def test_gate_summary_shape(client, monkeypatch):
    # no LLM / no network must be constructed on this route
    import orchestrator.tools.m5_writing as _m5
    monkeypatch.setattr(_m5, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no LLM")))
    pid = _user_and_project(client)
    r = client.get(f"/api/v1/projects/{pid}/gate-summary")
    assert r.status_code == 200
    gs = r.json()
    assert gs["deterministic"] is True and len(gs["items"]) == 11
    assert "coverage" in gs and "certificate" in gs
    assert gs["ready"] in (True, False)


def test_gate_summary_foreign_project_404(client):
    _user_and_project(client)   # authenticates client as user A
    r = client.get(f"/api/v1/projects/{uuid.uuid4()}/gate-summary")
    assert r.status_code == 404

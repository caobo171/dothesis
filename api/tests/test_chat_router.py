"""Tests for chat router project + thread CRUD."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Project, Thread, User


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _login_user(client) -> User:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        from app.security import create_session
        # create_session returns a signed cookie value; set with the correct
        # cookie name used by deps.py (opendraft_session).
        token = create_session(db, u)
    client.cookies.set("opendraft_session", token)
    return u


def test_create_project_returns_id_and_default_thread(client):
    _login_user(client)
    r = client.post("/api/v1/projects",
                    json={"name": "My Thesis", "field": "Marketing", "language": "vi"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body
    assert body["name"] == "My Thesis"

    sf = get_session_factory()
    with sf() as db:
        threads = db.query(Thread).filter_by(project_id=body["id"]).all()
        assert len(threads) == 1
        assert threads[0].name == "Main"


def test_get_project_returns_context_store_snapshot(client):
    _login_user(client)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    r = client.get(f"/api/v1/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["current_module"] == "M1"
    assert "context_store" in r.json()


def test_list_threads_for_project(client):
    _login_user(client)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    r = client.get(f"/api/v1/projects/{project_id}/threads")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_create_additional_thread_in_project(client):
    _login_user(client)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    r = client.post(f"/api/v1/projects/{project_id}/threads",
                    json={"name": "Alt methodology"})
    assert r.status_code == 200
    assert r.json()["name"] == "Alt methodology"
    threads = client.get(f"/api/v1/projects/{project_id}/threads").json()
    assert len(threads) == 2


def test_disabled_when_flag_off(monkeypatch):
    monkeypatch.delenv("ORCHESTRATOR_ENABLED", raising=False)
    c = TestClient(create_app())
    r = c.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404

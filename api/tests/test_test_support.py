"""Test-support router: the E2E harness's only backdoor into the API.

Runs on the existing testcontainers conftest (_bind_db creates the schema).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DOTHESIS_TEST_SUPPORT", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    # create_app() calls reset_settings(), so the env above takes effect.
    return TestClient(create_app())


def _make_user(client, email: str) -> str:
    """Real signup → test verify → real login. Returns the access token."""
    uname = "u" + uuid.uuid4().hex[:10]
    r = client.post("/api/v1/auth/signup",
                    json={"username": uname, "email": email, "password": "password-123"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/test/verify-email", json={"email": email})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/login",
                    json={"email": email, "password": "password-123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_router_absent_without_flag(monkeypatch):
    monkeypatch.delenv("DOTHESIS_TEST_SUPPORT", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    c = TestClient(create_app())
    r = c.post("/api/v1/test/verify-email", json={"email": "x@e2e.example.com"})
    assert r.status_code == 404  # route does not exist in prod-shaped config


def test_verify_email_unblocks_login_and_grants_bonus(client):
    email = "verify@e2e.example.com"
    uname = "verifyuser1"
    r = client.post("/api/v1/auth/signup",
                    json={"username": uname, "email": email, "password": "password-123"})
    assert r.status_code == 201
    # Unverified login is a 403 (auth.login) — proves signup stayed real.
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "password-123"})
    assert r.status_code == 403
    r = client.post("/api/v1/test/verify-email", json={"email": email})
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "password-123"})
    assert r.status_code == 200
    assert r.json()["user"]["credit"] > 0  # signup bonus granted like auth.verify does


def test_seed_project_writes_through_guarded_store(client, tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))
    tok = _make_user(client, "seed@e2e.example.com")
    r = client.post("/api/v1/test/seed-project", json={
        "access_token": tok,
        "name": "Seeded thesis",
        "slices": {
            "M1": {"research_title": "T", "research_questions": ["RQ1"]},
            "M4": {"analysis_results": "AVE=0.62 HTMT ok R2=.41"},
        },
        "done": ["M1"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    pid, tid = body["project_id"], body["thread_id"]
    assert uuid.UUID(pid) and uuid.UUID(tid)

    # Read back through the same guarded store the agent uses — proves the
    # seed took the real write path (status map + flat contextStore keys).
    from app.agent_state import DbProjectStateStore
    from app.db import get_engine
    store = DbProjectStateStore(get_engine(), uuid.UUID(pid), tmp_path)
    state = store.load()
    assert state["status"]["M1"] == "done"
    assert state["status"]["M4"] == "in_progress"
    assert state["contextStore"]["research_title"] == "T"
    assert state["contextStore"]["analysis_results"].startswith("AVE=0.62")


def test_seed_project_rejects_ownership_violation(client, tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))
    tok = _make_user(client, "seedbad@e2e.example.com")
    # literature_sources is owned by M2 — committing it under M1 must 422,
    # because the endpoint uses commit_slice's real ownership check.
    r = client.post("/api/v1/test/seed-project", json={
        "access_token": tok,
        "slices": {"M1": {"literature_sources": []}},
    })
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "bad_slice"


def test_set_credit_pins_the_balance(client):
    tok = _make_user(client, "broke@e2e.example.com")
    r = client.post("/api/v1/test/set-credit", json={"access_token": tok, "credit": 0})
    assert r.status_code == 200 and r.json()["credit"] == 0
    r = client.post("/api/v1/auth/me", json={"access_token": tok})
    assert r.status_code == 200 and r.json()["credit"] == 0

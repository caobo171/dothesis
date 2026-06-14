import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Project, User


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup(client) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True, credit=1000)
        db.add(u); db.commit()
        from app.security import create_session
        client.headers["Authorization"] = f"Bearer {create_session(db, u)}"
    return uuid.UUID(client.post("/api/v1/projects", json={"name": "T"}).json()["id"])


def test_post_run_spawns_orchestrator_subprocess(client, monkeypatch):
    pid = _setup(client)
    spawned = []

    def fake_spawn(db, run, brief, resume_from=None):
        run.pid = 12345
        run.status = "running"
        spawned.append({"mode": run.mode, "project_id": run.project_id,
                        "brief": brief, "resume_from": resume_from})

    monkeypatch.setattr("app.job_runner.spawn_orchestrator_run", fake_spawn)

    r = client.post(f"/api/v1/projects/{pid}/runs",
                    json={"mode": "auto", "topic": "Leadership in SMEs"})
    assert r.status_code == 200, r.text
    assert "run_id" in r.json()
    assert spawned[0]["mode"] == "auto"
    assert spawned[0]["brief"]["topic"] == "Leadership in SMEs"


def _mark_run(rid: str, **fields):
    sf = get_session_factory()
    with sf() as db:
        from app.models import Job
        run = db.get(Job, uuid.UUID(rid))
        for k, v in fields.items():
            setattr(run, k, v)
        db.commit()


def test_resume_failed_run_resumes_checkpoint(client, monkeypatch):
    """A failed run resumes from its checkpoint (resume_from == run.id) instead
    of restarting — and the stale error markers are cleared."""
    pid = _setup(client)
    spawned = []

    def fake_spawn(db, run, brief, resume_from=None):
        spawned.append(resume_from)
        run.status = "running"

    monkeypatch.setattr("app.job_runner.spawn_orchestrator_run", fake_spawn)

    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "x"}).json()["run_id"]
    _mark_run(rid, status="failed", error_text="orchestrator auto-draft failed")

    r = client.post(f"/api/v1/runs/{rid}/resume")
    assert r.status_code == 200, r.text
    assert spawned[-1] == rid  # resumed the SAME thread, not a fresh run

    sf = get_session_factory()
    with sf() as db:
        from app.models import Job
        run = db.get(Job, uuid.UUID(rid))
        assert run.error_text is None
        assert run.status == "running"


def test_resume_running_run_rejected(client, monkeypatch):
    """Resume is only for paused/failed/canceled — a live run is a 409."""
    pid = _setup(client)
    monkeypatch.setattr(
        "app.job_runner.spawn_orchestrator_run",
        lambda db, run, brief, resume_from=None: setattr(run, "status", "running"))
    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "x"}).json()["run_id"]
    _mark_run(rid, status="running")
    r = client.post(f"/api/v1/runs/{rid}/resume")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"]["code"] == "not_resumable"


def test_pause_run_calls_cancel(client, monkeypatch):
    pid = _setup(client)
    called = []

    def fake_cancel(db, job):
        called.append(job.id)
        job.status = "paused"

    monkeypatch.setattr("app.job_runner.spawn_orchestrator_run",
                        lambda db, run, brief, resume_from=None: setattr(run, "status", "running"))
    monkeypatch.setattr("app.job_runner.cancel_job", fake_cancel)

    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "x"}).json()["run_id"]
    r = client.post(f"/api/v1/runs/{rid}/pause")
    assert r.status_code == 200
    assert called

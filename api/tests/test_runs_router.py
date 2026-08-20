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


def _setup(client, **project_fields) -> uuid.UUID:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True, credit=1000)
        db.add(u); db.commit()
        from app.security import create_session
        client.headers["Authorization"] = f"Bearer {create_session(db, u)}"
    return uuid.UUID(client.post("/api/v1/projects",
                                 json={"name": "T", **project_fields}).json()["id"])


def test_post_run_spawns_the_headless_deep_agent(client, monkeypatch):
    """Auto-draft runs the deep agent headless, not the orchestrator graph."""
    pid = _setup(client)
    spawned = []

    def fake_spawn(db, run, params):
        run.pid = 12345
        run.status = "running"
        spawned.append({"mode": run.mode, "params": params})

    monkeypatch.setattr("app.job_runner.spawn_headless_run", fake_spawn)

    r = client.post(f"/api/v1/projects/{pid}/runs",
                    json={"mode": "auto", "topic": "Leadership in SMEs",
                          "language": "vi"})
    assert r.status_code == 200, r.text
    assert "run_id" in r.json()
    # Job.mode stays "auto" — it is the column the UI and admin screens read.
    # params["mode"] is the headless runner's own vocabulary.
    assert spawned[0]["mode"] == "auto"
    assert spawned[0]["params"]["mode"] == "full_thesis"
    assert spawned[0]["params"]["topic"] == "Leadership in SMEs"
    assert spawned[0]["params"]["language"] == "vi"


def _mark_run(rid: str, **fields):
    sf = get_session_factory()
    with sf() as db:
        from app.models import Job
        run = db.get(Job, uuid.UUID(rid))
        for k, v in fields.items():
            setattr(run, k, v)
        db.commit()


def test_resume_respawns_headless_over_committed_state(client, monkeypatch):
    """A failed run resumes by re-running a fresh agent over the state
    commit_slice already persisted — there is no checkpoint to re-enter — and
    the stale error markers are cleared."""
    # A Vietnamese thesis: the language lives on the PROJECT row, which is where
    # resume has to read it from — the resume POST carries no body of its own.
    pid = _setup(client, language="vi", citation_style="ieee")
    spawned = []
    monkeypatch.setattr("app.job_runner.spawn_headless_run",
                        lambda db, run, params: spawned.append(params))
    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "T"}).json()["run_id"]
    _mark_run(rid, status="failed", error_text="boom")

    r = client.post(f"/api/v1/runs/{rid}/resume")
    assert r.status_code == 200, r.text
    # Exactly two keys, and the equality check is the point — anything extra is
    # a param nothing reads, which is how the first version of this carried a
    # dead `citation_style` (not an M1-owned key; the Project row is what
    # exporters read).
    #
    # `language` is carried because _seed_brief commits it into the M1 slice
    # when that slice has none, and the export reads it back from there
    # (agent_state.py:407, default "vi"). `topic` is not, because _seed_brief
    # refuses to overwrite an existing research_title.
    assert spawned[-1] == {"mode": "full_thesis", "language": "vi"}

    sf = get_session_factory()
    with sf() as db:
        from app.models import Job
        run = db.get(Job, uuid.UUID(rid))
        assert run.error_text is None and run.finished_at is None


def test_resume_rejects_a_running_run(client, monkeypatch):
    pid = _setup(client)
    monkeypatch.setattr("app.job_runner.spawn_headless_run",
                        lambda db, run, params: None)
    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "T"}).json()["run_id"]
    _mark_run(rid, status="running")
    r = client.post(f"/api/v1/runs/{rid}/resume")
    assert r.status_code == 409


def _seed_run_with_backlog(client, monkeypatch, events) -> str:
    """Create a run that is already finished, with `events` waiting in the DB."""
    pid = _setup(client)
    # Stub the real spawner so the setup POST below doesn't shell out to the
    # headless subprocess — these tests only care about the SSE backlog replay,
    # not about what a live run would do.
    monkeypatch.setattr("app.job_runner.spawn_headless_run",
                        lambda db, run, params: setattr(run, "status", "running"))
    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "x"}).json()["run_id"]
    # status=done keeps the route from starting a monitor: the point of these
    # tests is the client that connects AFTER the run finished, so every event
    # it sees comes from the DB backlog and never from pubsub.
    _mark_run(rid, status="done")
    sf = get_session_factory()
    with sf() as db:
        from app.models import JobEvent
        for ev in events:
            db.add(JobEvent(job_id=uuid.UUID(rid), **ev))
        db.commit()
    return rid


def test_run_sse_ends_when_backlog_holds_terminal_event(client, monkeypatch):
    """Reaching the assertions at all is the real assertion: TestClient buffers
    the whole ASGI response before returning, so this call only comes back if
    the server ends the stream itself. The run finished before we connected, so
    its terminal event replays from the DB backlog, not pubsub — a client
    cannot read a few events and hang up to rescue a generator that never
    returns."""
    rid = _seed_run_with_backlog(client, monkeypatch, [
        {"type": "activity", "phase": "research", "agent": "Scout", "text": "hi"},
        {"type": "job_done"},
    ])
    r = client.post(f"/api/v1/runs/{rid}/events", json={})
    assert r.status_code == 200
    assert "activity" in r.text
    assert "job_done" in r.text
    # Nothing is emitted after the terminal event (no keepalive tail).
    assert "keepalive" not in r.text
    assert r.text.rstrip().endswith("}")


def test_run_sse_redacts_traceback_from_backlog(client, monkeypatch):
    """meta_json is merged into the SSE payload verbatim, so a server-side
    traceback stored for ops debugging must be stripped before it reaches the
    browser — same protection the jobs stream applies."""
    rid = _seed_run_with_backlog(client, monkeypatch, [
        {"type": "error", "text": "boom",
         "meta_json": {"traceback": "Traceback (most recent call last):\n  secret internals"}},
    ])
    r = client.post(f"/api/v1/runs/{rid}/events", json={})
    assert r.status_code == 200
    assert "boom" in r.text  # the user-facing message still goes through
    assert "traceback" not in r.text
    assert "secret internals" not in r.text


def test_pause_run_calls_cancel(client, monkeypatch):
    pid = _setup(client)
    called = []

    def fake_cancel(db, job):
        called.append(job.id)
        job.status = "paused"

    # Stub the real spawner so the setup POST below doesn't shell out to the
    # headless subprocess — this test only cares that /pause calls cancel_job.
    monkeypatch.setattr("app.job_runner.spawn_headless_run",
                        lambda db, run, params: setattr(run, "status", "running"))
    monkeypatch.setattr("app.job_runner.cancel_job", fake_cancel)

    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "x"}).json()["run_id"]
    r = client.post(f"/api/v1/runs/{rid}/pause")
    assert r.status_code == 200
    assert called

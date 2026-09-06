"""Tests for chat router project + thread CRUD."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ContextStore, Project, Thread, User


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
        # cookie name used by deps.py (dothesis_session).
        token = create_session(db, u)
    client.headers["Authorization"] = f"Bearer {token}"
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


def test_create_project_persists_auto_mode(client):
    # Auto Thesis chosen on /new must be stored on the project (not a one-shot
    # client flag) so reopening it re-enters the auto flow. The response echoes
    # it and a fresh read still reports it.
    _login_user(client)
    r = client.post("/api/v1/projects", json={"name": "Auto one", "mode": "auto"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["mode"] == "auto"

    sf = get_session_factory()
    with sf() as db:
        assert db.get(Project, uuid.UUID(pid)).mode == "auto"

    # A later read (the return visit) still sees the persisted mode.
    assert client.post(f"/api/v1/projects/{pid}").json()["mode"] == "auto"


def test_create_project_mode_defaults_to_none(client):
    # Omitting mode (headless/partner callers, legacy clients) leaves it NULL,
    # which the client reads as ordinary chat.
    _login_user(client)
    r = client.post("/api/v1/projects", json={"name": "Plain"})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] is None


def test_get_project_returns_context_store_snapshot(client):
    _login_user(client)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    # GET→POST migration: read-only route now POST (same path) so the auth
    # token never rides in a URL. Bearer header still authenticates.
    r = client.post(f"/api/v1/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["current_module"] == "M1"
    assert "context_store" in r.json()


def test_list_threads_for_project(client):
    _login_user(client)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    # GET→POST migration: list route renamed to /threads/list (POST).
    r = client.post(f"/api/v1/projects/{project_id}/threads/list")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_create_additional_thread_in_project(client):
    _login_user(client)
    project_id = client.post("/api/v1/projects", json={"name": "X"}).json()["id"]
    r = client.post(f"/api/v1/projects/{project_id}/threads",
                    json={"name": "Alt methodology"})
    assert r.status_code == 200
    assert r.json()["name"] == "Alt methodology"
    # GET→POST migration: list route renamed to /threads/list (POST).
    threads = client.post(f"/api/v1/projects/{project_id}/threads/list").json()
    assert len(threads) == 2


def test_disabled_when_flag_off(monkeypatch):
    # setenv, not delenv: Settings reads a real .env file (which sets the flag
    # true on dev machines), so unsetting the process env only falls through to
    # the file and leaves the router mounted — the test then saw chat's 401
    # instead of the 404 it was written for, and only passed on hosts with no
    # .env. An explicit "false" outranks the file. create_app() calls
    # reset_settings(), so no cache to clear here.
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "false")
    c = TestClient(create_app())
    # GET→POST migration: get_project is now POST (same path). The disabled
    # flag → 404 intent is unchanged via the same route.
    r = c.post("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_list_projects_returns_slice_status_not_full_bodies(client):
    """The list read must stay light: slice STATUS only, never slice content.

    Regression guard. This endpoint has been made slow twice by loading whole
    m1–m5 JSONB per project — once via a per-row N+1, then via a batch load
    that still shipped every slice body. In production one account with 46
    projects produced a 3.8 MB response (~20s on a mobile downlink) to render
    module badges that read exactly one field per slice. The full slices are
    still served by the single-project read, which is what the chat UI uses.
    """
    u = _login_user(client)
    pid = client.post("/api/v1/projects", json={"name": "Heavy"}).json()["id"]

    sf = get_session_factory()
    with sf() as db:
        cs = db.get(ContextStore, uuid.UUID(pid))
        cs.m1_topic = {"confirmed_at": "2026-01-01T00:00:00Z",
                       "research_title": "T", "objectives": ["a", "b"]}
        # Started but never confirmed — must stay distinguishable from absent.
        cs.m2_literature = {"papers": [{"title": "p"} for _ in range(50)]}
        cs.m5_writing = {"chapters": {"c1": "x" * 100_000}}
        db.commit()

    body = client.post("/api/v1/projects/list").json()
    assert len(body) == 1
    store = body[0]["context_store"]

    # Status survives: confirmed slice reports its timestamp, plus the ONE small
    # body field the homepage cards need — the M1 research title. Both are single
    # extracted strings, not the JSONB body.
    assert store["m1_topic"] == {"confirmed_at": "2026-01-01T00:00:00Z",
                                 "research_title": "T"}
    # ...an unconfirmed-but-present slice is an object with a null timestamp...
    assert store["m2_literature"] == {"confirmed_at": None}
    # ...and an absent slice stays None (never {} or a stub).
    assert store["m3_design"] is None

    # The HEAVY bodies still do NOT leak — only research_title is whitelisted.
    assert "objectives" not in store["m1_topic"]
    assert store["m5_writing"] == {"confirmed_at": None}
    assert "x" * 1000 not in client.post("/api/v1/projects/list").text

    # The single-project read still carries the full slices.
    full = client.post(f"/api/v1/projects/{pid}").json()["context_store"]
    assert full["m1_topic"]["research_title"] == "T"
    assert len(full["m5_writing"]["chapters"]["c1"]) == 100_000


# --- the project's credit total --------------------------------------------
#
# "Tổng credits dự án" summed Message.cost_credits joined through threads, so it
# counted chat turns and nothing else. A project whose entire cost came from an
# Auto Thesis run — 3,734 credits on the measured one — displayed 0, and that is
# the most expensive thing this product does.
#
# credit_transactions is the billing truth ("Every balance change has a matching
# ledger row", credit_ledger.py) and it is what the Transactions page and the
# user's balance are built from. Message.cost_credits is a per-message display
# value that has drifted from it on real threads (18 vs 36, 10150 vs 9561).

def _project_with_thread(client):
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.post(f"/api/v1/projects/{pid}/threads", json={"name": "Main"}).json()["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def _ledger(user_id, *, delta, reason, ref_type, ref_id):
    from app.models import CreditTransaction
    sf = get_session_factory()
    with sf() as db:
        db.add(CreditTransaction(user_id=user_id, delta=delta, reason=reason,
                                 ref_type=ref_type, ref_id=ref_id))
        db.commit()


def test_an_auto_run_counts_toward_the_project_total(client):
    from app.models import Job
    u = _login_user(client)
    pid, _ = _project_with_thread(client)
    run_id = uuid.uuid4()
    sf = get_session_factory()
    with sf() as db:
        db.add(Job(id=run_id, project_id=pid, mode="auto", status="done"))
        db.commit()
    _ledger(u.id, delta=-3734, reason="auto_run", ref_type="run", ref_id=run_id)

    body = client.post(f"/api/v1/projects/{pid}/credits").json()

    assert body["total_credits"] == 3734


def test_chat_turns_still_count(client):
    u = _login_user(client)
    pid, tid = _project_with_thread(client)
    _ledger(u.id, delta=-120, reason="chat_turn", ref_type="thread", ref_id=tid)

    assert client.post(f"/api/v1/projects/{pid}/credits").json()["total_credits"] == 120


def test_a_run_and_a_conversation_add_up(client):
    from app.models import Job
    u = _login_user(client)
    pid, tid = _project_with_thread(client)
    run_id = uuid.uuid4()
    sf = get_session_factory()
    with sf() as db:
        db.add(Job(id=run_id, project_id=pid, mode="auto", status="done"))
        db.commit()
    _ledger(u.id, delta=-3734, reason="auto_run", ref_type="run", ref_id=run_id)
    _ledger(u.id, delta=-120, reason="chat_turn", ref_type="thread", ref_id=tid)

    assert client.post(f"/api/v1/projects/{pid}/credits").json()["total_credits"] == 3854


def test_another_project_does_not_leak_in(client):
    u = _login_user(client)
    mine, _ = _project_with_thread(client)
    _, theirs_tid = _project_with_thread(client)
    _ledger(u.id, delta=-500, reason="chat_turn", ref_type="thread", ref_id=theirs_tid)

    assert client.post(f"/api/v1/projects/{mine}/credits").json()["total_credits"] == 0


def test_a_top_up_is_not_project_spend(client):
    """Deltas are signed: a purchase is positive and belongs to nobody's
    project. Summing them raw would show a project that REFUNDED credits."""
    u = _login_user(client)
    pid, tid = _project_with_thread(client)
    _ledger(u.id, delta=-100, reason="chat_turn", ref_type="thread", ref_id=tid)
    _ledger(u.id, delta=50_000, reason="admin_grant", ref_type="user", ref_id=u.id)

    assert client.post(f"/api/v1/projects/{pid}/credits").json()["total_credits"] == 100

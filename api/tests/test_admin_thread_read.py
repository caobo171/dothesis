"""Super-admin read access to any thread, for debugging.

The rule under test is an ASYMMETRY, and the write half matters more than the
read half: an admin must be able to open a student's thread to see why a run
went wrong, and must NOT be able to post into it. Posting would spend the
student's credits, append to their visible history, and mutate the graph
checkpoint under them — a debugging tool that edits the thing being debugged.

`readable_project` also answers 404 rather than 403 for a project a normal user
can't see, so the endpoint never becomes an oracle for "does this id exist".
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Message, Project, Thread
from tests.conftest import make_user

# admin_config._SEED — the allowlist is by email, so the fixture user must use
# one of these to BE an admin.
ADMIN_EMAIL = "cao.nv17@gmail.com"


@pytest.fixture
def world():
    """A student with a project + thread, an admin, and an unrelated user."""
    Session = get_session_factory()
    with Session() as s:
        student = make_user(s, email="student@e.com")
        admin = make_user(s, email=ADMIN_EMAIL)
        stranger = make_user(s, email="stranger@e.com")
        p = Project(user_id=student.id, name="Their thesis",
                    current_module="M1", status="draft")
        s.add(p); s.flush()
        t = Thread(project_id=p.id, name="Main",
                   langgraph_thread_id=str(uuid.uuid4()), status="active")
        s.add(t); s.flush()
        s.add(Message(thread_id=t.id, role="user", content="why is my run broken"))
        s.commit()
        for u in (student, admin, stranger):
            s.refresh(u); s.expunge(u)
        return {"student": student, "admin": admin, "stranger": stranger,
                "pid": str(p.id), "tid": str(t.id)}


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


# --- the read half ----------------------------------------------------------

def test_admin_can_open_someone_elses_thread(world):
    r = _as(world["admin"]).post(f"/api/v1/threads/{world['tid']}",
                                 json={"access_token": "x"})
    assert r.status_code == 200
    assert r.json()["name"] == "Main"


def test_admin_can_read_the_messages(world):
    """The actual debugging payload — without this the page renders empty."""
    r = _as(world["admin"]).post(f"/api/v1/threads/{world['tid']}/messages/list",
                                 json={"access_token": "x"})
    assert r.status_code == 200
    assert any("why is my run broken" in str(m) for m in r.json())


@pytest.mark.parametrize("path", [
    "/api/v1/projects/{pid}",
    "/api/v1/projects/{pid}/threads/list",
    "/api/v1/projects/{pid}/credits",
    "/api/v1/projects/{pid}/uploads/list",
])
def test_admin_can_load_the_rest_of_the_page(world, path):
    """The thread page's layout fans out to all of these. One 404 and the user
    sees a half-rendered shell, which is what 'nothing showing' looked like."""
    r = _as(world["admin"]).post(path.format(pid=world["pid"]),
                                 json={"access_token": "x"})
    assert r.status_code == 200, path


def test_owner_still_reads_their_own_thread(world):
    r = _as(world["student"]).post(f"/api/v1/threads/{world['tid']}",
                                   json={"access_token": "x"})
    assert r.status_code == 200


# --- the write half, which must NOT open up ---------------------------------

def test_admin_cannot_post_a_message_into_someone_elses_thread(world):
    """The whole point of the read/write split. A debugging view that can write
    spends the student's credits and mutates the checkpoint being debugged."""
    r = _as(world["admin"]).post(
        f"/api/v1/threads/{world['tid']}/messages",
        json={"access_token": "x", "text": "hello from support"})
    # 404, not 422: the body must be VALID or this asserts nothing — a schema
    # rejection would pass the test while the ownership check never ran.
    assert r.status_code == 404, f"got {r.status_code}: {r.text[:200]}"


def test_admin_cannot_create_a_thread_in_someone_elses_project(world):
    r = _as(world["admin"]).post(f"/api/v1/projects/{world['pid']}/threads",
                                 json={"access_token": "x", "name": "admin thread"})
    assert r.status_code == 404


# --- everyone else is unchanged ---------------------------------------------

def test_a_normal_user_still_cannot_see_another_thread(world):
    r = _as(world["stranger"]).post(f"/api/v1/threads/{world['tid']}",
                                    json={"access_token": "x"})
    assert r.status_code == 404


def test_a_normal_user_gets_404_not_403(world):
    """404, so the response can't be used to probe which project ids exist."""
    r = _as(world["stranger"]).post(f"/api/v1/projects/{world['pid']}",
                                    json={"access_token": "x"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "not_found"


def test_a_missing_project_is_404_for_an_admin_too(world):
    r = _as(world["admin"]).post(f"/api/v1/projects/{uuid.uuid4()}",
                                 json={"access_token": "x"})
    assert r.status_code == 404

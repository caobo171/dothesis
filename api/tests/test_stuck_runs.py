"""A run row outlives its process. Nothing may treat one as live forever.

A row only leaves `running` in its own process's `finally`. When the citation
search hung — no enforced timeout, output to /dev/null — the row stayed
`running` indefinitely, and /tools/runs/active kept handing it to the next
screen the student opened as their live job. The spinner was for work that was
never coming back.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import ToolRun, User
from app.routers.tools import _ACTIVE_RUN_MAX_AGE_S
from app.security import create_session


@pytest.fixture
def client():
    return TestClient(create_app())


def _login(client) -> tuple[uuid.UUID, str]:
    """Returns (user_id, token). The token goes in the BODY — every endpoint here
    is POST precisely so the auth token has somewhere to ride (CLAUDE.md)."""
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit(); db.refresh(u)
        token = create_session(db, u)
        client.headers["Authorization"] = f"Bearer {token}"
        return u.id, token


def _running(user_id, *, age_s: int, tool="citation-search") -> int:
    sf = get_session_factory()
    with sf() as db:
        row = ToolRun(user_id=user_id, surface="web", tool=tool, status="running",
                      ok=False, progress_done=1, progress_total=3,
                      created_at=datetime.now(timezone.utc) - timedelta(seconds=age_s))
        db.add(row); db.commit(); db.refresh(row)
        return row.id


def _active(client, token) -> dict:
    r = client.post("/api/v1/tools/runs/active", json={"access_token": token})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_fresh_running_row_is_reported(client):
    uid, token = _login(client)
    rid = _running(uid, age_s=30)
    out = _active(client, token)
    assert out["id"] == str(rid) and out["total"] == 3


def test_a_run_older_than_any_job_is_not_reported(client):
    """The hung-citation-search case."""
    uid, token = _login(client)
    _running(uid, age_s=_ACTIVE_RUN_MAX_AGE_S + 60)
    assert _active(client, token)["id"] is None, "a dead run was reported as the user's live one"


def test_a_stale_row_does_not_hide_a_live_one(client):
    """The stale row can be the NEWEST by id — inserted last after an earlier
    job is still going. Ordering by id alone would return it and report the
    live job as nothing at all."""
    uid, token = _login(client)
    _running(uid, age_s=30, tool="humanize-docx")
    _running(uid, age_s=_ACTIVE_RUN_MAX_AGE_S + 60)
    assert _active(client, token)["tool"] == "humanize-docx"

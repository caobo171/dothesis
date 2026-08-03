"""Admin view of MCP connector usage — routers/admin_connectors.py.

The point of these endpoints is that the uvicorn access log can't answer "who
used the connector, how much, and did it work?". So the tests worth having are
the ones about attribution (the right email on the right call), about failures
being visible rather than filtered out, and about the endpoints being admin-only
— an audit trail that any user can read is its own privacy problem.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import McpOAuthClient, McpOAuthRefreshToken, McpToolCall
from tests.conftest import make_user

ADMIN_EMAIL = "cao.nv17@gmail.com"  # admin_config._SEED


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def world():
    Session = get_session_factory()
    with Session() as s:
        admin = make_user(s, email=ADMIN_EMAIL)
        alice = make_user(s, email="alice@e.com")
        bob = make_user(s, email="bob@e.com")
        s.add(McpOAuthClient(client_id="dt_claude", client_name="Claude",
                             redirect_uris=["https://claude.ai/cb"], auth_method="none"))
        s.flush()
        s.add(McpOAuthRefreshToken(
            token_hash="rt-alice", client_id="dt_claude", user_id=alice.id,
            scope="dothesis:mcp", expires_at=_now() + timedelta(days=30)))
        # Alice: two good calls and one refusal. Bob: one good call.
        for ok, err, chars in ((True, None, 900), (True, None, 300),
                               (False, "no_anchor", 120)):
            s.add(McpToolCall(user_id=alice.id, client_id="dt_claude", tool="humanize",
                              ok=ok, error=err, duration_ms=2500,
                              input_chars=chars, output_chars=chars if ok else 0))
        s.add(McpToolCall(user_id=bob.id, client_id="dt_claude", tool="humanize",
                          ok=True, error=None, duration_ms=1000,
                          input_chars=50, output_chars=50))
        s.commit()
        for u in (admin, alice, bob):
            s.refresh(u); s.expunge(u)
        return {"admin": admin, "alice": alice, "bob": bob}


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def test_calls_are_attributed_to_the_right_user(world):
    r = _as(world["admin"]).post("/api/v1/admin/connectors/calls",
                                 json={"access_token": "x"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert r.json()["total"] == 4
    assert {i["user_email"] for i in items} == {"alice@e.com", "bob@e.com"}
    assert all(i["tool"] == "humanize" for i in items)


def test_failed_calls_are_visible_not_filtered_out(world):
    """A success-only log hides the thing an admin is usually looking for."""
    r = _as(world["admin"]).post("/api/v1/admin/connectors/calls",
                                 json={"access_token": "x", "ok": False})
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["error"] == "no_anchor"
    assert items[0]["user_email"] == "alice@e.com"


def test_calls_can_be_filtered_to_one_user(world):
    r = _as(world["admin"]).post(
        "/api/v1/admin/connectors/calls",
        json={"access_token": "x", "user_id": str(world["alice"].id)})
    assert r.json()["total"] == 3
    assert all(i["user_email"] == "alice@e.com" for i in r.json()["items"])


def test_calls_are_newest_first(world):
    items = _as(world["admin"]).post("/api/v1/admin/connectors/calls",
                                     json={"access_token": "x"}).json()["items"]
    stamps = [i["created_at"] for i in items]
    assert stamps == sorted(stamps, reverse=True)


def test_no_prose_is_returned_only_sizes(world):
    """The table stores sizes, never the text. If a 'content' field ever appears
    here it means the storage decision was quietly reversed."""
    item = _as(world["admin"]).post("/api/v1/admin/connectors/calls",
                                    json={"access_token": "x"}).json()["items"][0]
    assert "input_chars" in item and "output_chars" in item
    assert not any(k in item for k in ("text", "content", "input", "output"))


def test_summary_totals_per_user(world):
    r = _as(world["admin"]).post("/api/v1/admin/connectors/summary",
                                 json={"access_token": "x"})
    assert r.status_code == 200
    body = r.json()
    alice = next(u for u in body["users"] if u["user_email"] == "alice@e.com")
    assert alice["calls"] == 3
    assert alice["failed"] == 1
    assert alice["input_chars"] == 1320
    assert body["totals"]["calls"] == 4
    assert body["totals"]["users_with_calls"] == 2


def test_summary_lists_live_grants_separately_from_usage(world):
    """Connected-but-never-used is the interesting drop-off for the giveaway, so
    grants are counted independently of calls."""
    body = _as(world["admin"]).post("/api/v1/admin/connectors/summary",
                                    json={"access_token": "x"}).json()
    assert body["totals"]["live_grants"] == 1
    assert body["grants"][0]["user_email"] == "alice@e.com"
    assert body["grants"][0]["client_name"] == "Claude"
    # Bob has calls but no live grant, and still appears in usage.
    assert any(u["user_email"] == "bob@e.com" for u in body["users"])


@pytest.mark.parametrize("path", ["/api/v1/admin/connectors/calls",
                                  "/api/v1/admin/connectors/summary"])
def test_a_normal_user_cannot_read_the_audit_trail(world, path):
    """An audit log everyone can read is its own privacy problem."""
    r = _as(world["alice"]).post(path, json={"access_token": "x"})
    assert r.status_code == 403


def test_page_size_is_capped(world):
    """Unbounded page_size makes the endpoint a way to pull the whole table in
    one request."""
    r = _as(world["admin"]).post("/api/v1/admin/connectors/calls",
                                 json={"access_token": "x", "page_size": 100000})
    assert r.json()["page_size"] == 200

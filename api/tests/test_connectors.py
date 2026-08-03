"""Connected AI apps — list + revoke (routers/connectors.py).

These endpoints only became possible when the MCP OAuth grants moved out of a
SQLite file beside the MCP process and into DoThesis's own database. The tests
that matter here are the isolation ones: `client_id` is caller-supplied and is
SHARED across every user of that AI client (Claude registers once per
workspace), so a revoke that matched on it alone would disconnect strangers.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import McpOAuthClient, McpOAuthCode, McpOAuthRefreshToken
from tests.conftest import make_user


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def users():
    Session = get_session_factory()
    with Session() as s:
        a = make_user(s, email="a@e.com")
        b = make_user(s, email="b@e.com")
        s.commit()
        for u in (a, b):
            s.refresh(u)
            s.expunge(u)
        return a, b


def _client_row(s, client_id="dt_claude", name="Claude"):
    s.add(McpOAuthClient(
        client_id=client_id, client_name=name,
        redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
        auth_method="none"))


def _grant(s, user, client_id="dt_claude", *, token_hash=None,
           revoked=False, days=30, created_days_ago=0):
    s.add(McpOAuthRefreshToken(
        token_hash=token_hash or f"h-{user.email}-{client_id}-{created_days_ago}-{revoked}",
        client_id=client_id, user_id=user.id, scope="dothesis:mcp",
        created_at=_now() - timedelta(days=created_days_ago),
        expires_at=_now() + timedelta(days=days), revoked=revoked))


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def test_list_shows_a_connected_client(users):
    alice, _ = users
    Session = get_session_factory()
    with Session() as s:
        _client_row(s)
        _grant(s, alice)
        s.commit()

    r = _as(alice).post("/api/v1/connectors/list", json={"access_token": "x"})
    assert r.status_code == 200
    got = r.json()["connectors"]
    assert len(got) == 1
    assert got[0]["client_id"] == "dt_claude"
    assert got[0]["client_name"] == "Claude"


def test_list_collapses_rotated_tokens_into_one_connection(users):
    """Every refresh rotates a token out and a new one in. Listing rows would
    show one 'connection' per refresh, which is nonsense to a reader."""
    alice, _ = users
    Session = get_session_factory()
    with Session() as s:
        _client_row(s)
        _grant(s, alice, token_hash="old", created_days_ago=5)
        _grant(s, alice, token_hash="new", created_days_ago=0)
        s.commit()

    got = _as(alice).post("/api/v1/connectors/list", json={"access_token": "x"}).json()["connectors"]
    assert len(got) == 1
    # "Connected at" should be when the grant STARTED, not when it last renewed.
    assert got[0]["connected_at"] < (_now() - timedelta(days=4)).isoformat()


def test_list_hides_revoked_and_expired_grants(users):
    alice, _ = users
    Session = get_session_factory()
    with Session() as s:
        _client_row(s)
        _client_row(s, "dt_gone", "Old App")
        _grant(s, alice, "dt_claude", revoked=True)
        _grant(s, alice, "dt_gone", days=-1)
        s.commit()

    assert _as(alice).post("/api/v1/connectors/list",
                           json={"access_token": "x"}).json()["connectors"] == []


def test_list_does_not_leak_another_users_connection(users):
    """The client_id is shared across every user of that AI client, so this is
    the case a naive query gets wrong."""
    alice, bob = users
    Session = get_session_factory()
    with Session() as s:
        _client_row(s)
        _grant(s, bob)
        s.commit()

    assert _as(alice).post("/api/v1/connectors/list",
                           json={"access_token": "x"}).json()["connectors"] == []


def test_revoke_ends_only_the_callers_grant(users):
    alice, bob = users
    Session = get_session_factory()
    with Session() as s:
        _client_row(s)
        _grant(s, alice)
        _grant(s, bob)
        s.commit()

    r = _as(alice).post("/api/v1/connectors/revoke",
                        json={"access_token": "x", "client_id": "dt_claude"})
    assert r.status_code == 200
    assert r.json()["revoked"] == 1

    # Alice is disconnected...
    assert _as(alice).post("/api/v1/connectors/list",
                           json={"access_token": "x"}).json()["connectors"] == []
    # ...and Bob, who shares the client_id, is untouched.
    assert len(_as(bob).post("/api/v1/connectors/list",
                             json={"access_token": "x"}).json()["connectors"]) == 1


def test_revoke_also_burns_an_unredeemed_code(users):
    """A pending auth code is still exchangeable for a fresh token, which would
    silently undo the revoke seconds after the user asked for it."""
    alice, _ = users
    Session = get_session_factory()
    with Session() as s:
        _client_row(s)
        _grant(s, alice)
        s.add(McpOAuthCode(
            code_hash="pending", client_id="dt_claude", user_id=alice.id,
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            code_challenge="c", scope="dothesis:mcp",
            expires_at=_now() + timedelta(seconds=60)))
        s.commit()

    _as(alice).post("/api/v1/connectors/revoke",
                    json={"access_token": "x", "client_id": "dt_claude"})

    with Session() as s:
        assert s.get(McpOAuthCode, "pending") is None


def test_revoking_something_not_connected_is_a_no_op(users):
    alice, _ = users
    r = _as(alice).post("/api/v1/connectors/revoke",
                        json={"access_token": "x", "client_id": "dt_nothing"})
    assert r.status_code == 200
    assert r.json()["revoked"] == 0


def test_revoke_is_honest_that_live_tokens_outlive_it(users):
    """The access token is a stateless JWT — nothing can recall it. The response
    says so rather than leaving the UI to invent a reassuring phrasing."""
    alice, _ = users
    r = _as(alice).post("/api/v1/connectors/revoke",
                        json={"access_token": "x", "client_id": "dt_claude"})
    assert "within the hour" in r.json()["detail"]

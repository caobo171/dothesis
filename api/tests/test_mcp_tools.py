"""The MCP tool surface — mcp/tools.py registry, dispatch, and rate limiting.

The registry replaced a single hardcoded `humanize` branch, so the tests worth
having are the ones that break when a new tool is added carelessly: every tool
must forward to a real endpoint as the calling user, every outcome must be
audited, and the rate limiter must be per-tier so a burst of cheap reads cannot
lock someone out of the model call they actually came for.
"""
import importlib
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from tests.conftest import make_user

MCP_DIR = Path(__file__).resolve().parents[2] / "mcp"
SECRET = "test-session-secret-for-mcp-oauth"


@pytest.fixture()
def user_id(pg_url):
    with Session(get_engine()) as s:
        u = make_user(s)
        s.commit()
        return str(u.id)


@pytest.fixture()
def mcp(monkeypatch, pg_url):
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DOTHESIS_MCP_REQUIRE_AUTH", "1")
    monkeypatch.syspath_prepend(str(MCP_DIR))
    for name in ("oauth", "audit", "ratelimit", "tools", "server_lite"):
        sys.modules.pop(name, None)
    mods = {n: importlib.import_module(n)
            for n in ("oauth", "ratelimit", "tools", "server_lite")}
    yield mods
    for name in ("oauth", "audit", "ratelimit", "tools", "server_lite"):
        sys.modules.pop(name, None)


def _bearer(user_id, client_id="dt_test"):
    import jwt
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + 600,
                       "typ": "mcp", "client_id": client_id},
                      SECRET, algorithm="HS256")


@pytest.fixture()
def client(mcp):
    from starlette.testclient import TestClient
    with TestClient(mcp["server_lite"].app, base_url="https://app.dothesis.com") as c:
        c.headers.update({"X-Forwarded-Proto": "https", "Host": "app.dothesis.com"})
        yield c


def _call(client, user_id, name, args=None):
    return client.post("/mcp", headers={"Authorization": f"Bearer {_bearer(user_id)}"},
                       json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": args or {}}})


# --- the registry -----------------------------------------------------------

def test_a_token_with_a_malformed_sub_is_rejected(client):
    """Everything downstream treats `sub` as a users.id — the audit INSERT casts
    it to uuid. Letting a malformed one through trades a clean 401 for a failed
    audit write and a confusing error from the API."""
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={"Authorization": f"Bearer {_bearer('not-a-uuid')}"})
    assert r.status_code == 401


def test_tools_list_matches_the_registry(client, user_id, mcp):
    r = client.post("/mcp", headers={"Authorization": f"Bearer {_bearer(user_id)}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in r.json()["result"]["tools"]]
    assert names == [t.name for t in mcp["tools"].TOOLS]
    assert "humanize" in names and "verify_citation" in names


def test_every_tool_declares_a_known_tier(mcp):
    """The tier drives the rate limit. A typo'd tier would silently disable
    limiting for that tool."""
    assert set(t.tier for t in mcp["tools"].TOOLS) <= set(mcp["ratelimit"].LIMITS)


def test_every_tool_builds_a_request_from_empty_args(mcp):
    """A KeyError inside request() would surface as an opaque 500 mid-chat."""
    for t in mcp["tools"].TOOLS:
        path, body = t.request({})
        assert path.startswith("/api/v1/"), t.name
        assert isinstance(body, dict), t.name


def test_an_unknown_tool_is_a_clean_protocol_error(client, user_id):
    r = _call(client, user_id, "definitely_not_a_tool")
    assert r.json()["error"]["code"] == -32602


# --- dispatch ---------------------------------------------------------------

def test_a_tool_forwards_to_its_endpoint_with_the_callers_bearer(client, user_id, mcp, monkeypatch):
    seen = {}

    async def _fake(tool, args, token):
        seen["path"], seen["body"] = tool.request(args)
        seen["token"] = token
        return {"ok": True, "text": "done"}
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)

    _call(client, user_id, "verify_citation", {"reference": "10.1/x"})
    assert seen["path"] == "/api/v1/tools/verify-citation"
    assert seen["body"] == {"reference": "10.1/x"}
    # The caller's own token, so the API applies their auth and quotas.
    # Compare CLAIMS, not the encoded string: _bearer() stamps iat/exp from the
    # clock, so re-minting here to compare would fail whenever a second ticks
    # between the call and the assertion. (It did, intermittently.)
    import jwt
    claims = jwt.decode(seen["token"], SECRET, algorithms=["HS256"])
    assert claims["sub"] == user_id
    assert claims["client_id"] == "dt_test"


def test_an_api_error_is_surfaced_not_swallowed(client, user_id, mcp, monkeypatch):
    """insufficient_credit is something the student can act on; an httpx
    traceback is not."""
    async def _fake(tool, args, token):
        raise mcp["server_lite"].ToolError(
            402, {"error": {"code": "insufficient_credit", "required": 50}})
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)

    r = _call(client, user_id, "start_thesis", {"topic": "x"})
    res = r.json()["result"]
    assert res["isError"] is True
    assert "insufficient_credit" in res["content"][0]["text"]


def test_a_list_returning_tool_omits_structured_content(client, user_id, mcp, monkeypatch):
    """structuredContent must be an object per the MCP schema — shipping a list
    there is the kind of thing a strict client rejects outright."""
    async def _fake(tool, args, token):
        return [{"id": "1", "name": "My thesis"}]
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)

    res = _call(client, user_id, "list_projects").json()["result"]
    assert "structuredContent" not in res
    assert "My thesis" in res["content"][0]["text"]
    assert res["isError"] is False


def test_id_arguments_are_not_counted_as_text_volume(client, user_id, mcp, monkeypatch, pg_url):
    """Otherwise list_projects/project_status look as heavy as a humanize in the
    admin view."""
    async def _fake(tool, args, token):
        return {"ok": True}
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)

    _call(client, user_id, "project_status", {"project_id": "a" * 36})
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(pg_url.replace("postgresql+psycopg://", "postgresql://"),
                         row_factory=dict_row) as c:
        row = c.execute("SELECT * FROM mcp_tool_calls WHERE user_id = %s::uuid",
                        (user_id,)).fetchone()
    assert row["tool"] == "project_status"
    assert row["input_chars"] == 0


# --- rate limiting ----------------------------------------------------------

def test_the_model_tier_throttles_after_its_budget(client, user_id, mcp, monkeypatch):
    async def _fake(tool, args, token):
        return {"ok": True, "text": "ok"}
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)
    monkeypatch.setitem(mcp["ratelimit"].LIMITS, "model", (3, 10))

    for _ in range(3):
        assert _call(client, user_id, "humanize", {"text": "x"}).json()["result"]["isError"] is False
    blocked = _call(client, user_id, "humanize", {"text": "x"}).json()["result"]
    assert blocked["isError"] is True
    assert "Rate limit" in blocked["content"][0]["text"]


def test_cheap_reads_do_not_consume_the_model_budget(client, user_id, mcp, monkeypatch):
    """Per-tier counting. A chat client polling list_projects must never lock a
    student out of the humanize they came for."""
    async def _fake(tool, args, token):
        return {"ok": True, "text": "ok"}
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)
    monkeypatch.setitem(mcp["ratelimit"].LIMITS, "model", (2, 10))
    monkeypatch.setitem(mcp["ratelimit"].LIMITS, "light", (50, 10))

    for _ in range(10):
        _call(client, user_id, "check_credits")
    assert _call(client, user_id, "humanize", {"text": "x"}).json()["result"]["isError"] is False


def test_a_throttled_call_is_still_audited(client, user_id, mcp, monkeypatch, pg_url):
    """"Why did nothing happen?" has to be answerable from /admin/connectors."""
    async def _fake(tool, args, token):
        return {"ok": True, "text": "ok"}
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)
    monkeypatch.setitem(mcp["ratelimit"].LIMITS, "model", (1, 10))

    _call(client, user_id, "humanize", {"text": "x"})
    _call(client, user_id, "humanize", {"text": "x"})

    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(pg_url.replace("postgresql+psycopg://", "postgresql://"),
                         row_factory=dict_row) as c:
        rows = c.execute("SELECT * FROM mcp_tool_calls WHERE user_id = %s::uuid "
                         "ORDER BY id", (user_id,)).fetchall()
    assert [r["error"] for r in rows] == [None, "rate_limited"]


def test_the_limiter_fails_open(client, user_id, mcp, monkeypatch):
    """A database hiccup must not read to a student as 'you are blocked'."""
    async def _fake(tool, args, token):
        return {"ok": True, "text": "ok"}
    monkeypatch.setattr(mcp["server_lite"], "_call_tool", _fake)

    def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(mcp["ratelimit"], "_dsn", _boom)

    assert _call(client, user_id, "humanize", {"text": "x"}).json()["result"]["isError"] is False

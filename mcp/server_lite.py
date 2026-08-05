"""DoThesis MCP server — SDK-free (Starlette only), for hosts where the MCP SDK
isn't installable (offline pip index) or where sharing DoThesis's venv must not
pull the SDK's pydantic>=2.12.

Implements the minimum of the Streamable-HTTP MCP protocol needed to expose the
`humanize` tool: `initialize`, `notifications/initialized`, `tools/list`,
`tools/call`, `ping`. Responses are plain JSON (the spec permits a JSON response
when the server doesn't stream). This — not the fastmcp `server.py` — is what
runs in production: one synchronous tool needs no more protocol than this, and
staying inside the API's venv removes the fastmcp/pinned-pydantic conflict
outright instead of isolating around it.

Auth: every /mcp request must carry `Authorization: Bearer <token>` issued by
oauth.py. An unauthenticated request gets 401 plus the `WWW-Authenticate:
Bearer resource_metadata=...` header — that header is how an MCP client
discovers the authorization server and starts the login flow, so it is load-
bearing, not decoration. The token is a DoThesis access token for the user who
consented, and it is FORWARDED verbatim to /api/v1/humanize: the call then runs
as that user, against their credits, through the API's normal auth path. This
server does not need to know anything about accounts.

Run (the API's venv already has starlette+uvicorn+httpx+PyJWT):
    export DOTHESIS_API_URL=http://localhost:7100
    export SESSION_SECRET=<same secret as the API>
    ../api/.venv/bin/python server_lite.py          # 127.0.0.1:9000/mcp
"""
from __future__ import annotations

import json
import logging
import os
import time

import httpx
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

import audit
import oauth
import ratelimit
import tools as toolreg

API_URL = os.getenv("DOTHESIS_API_URL", "http://localhost:7100").rstrip("/")
DEFAULT_PROTOCOL = "2025-06-18"

# The pre-OAuth escape hatch: one static token acting as one real user. It is
# now OFF unless explicitly asked for, and it was never safe to expose — see the
# "DEV ONLY, NOT SECURE YET" note this replaces in README.md. Setting
# DOTHESIS_MCP_REQUIRE_AUTH=0 on a public host hands that user's account to
# anyone who finds the URL.
REQUIRE_AUTH = os.getenv("DOTHESIS_MCP_REQUIRE_AUTH", "1") != "0"
DEV_TOKEN = os.getenv("DOTHESIS_ACCESS_TOKEN", "")

async def _call_tool(tool: toolreg.Tool, args: dict, token: str) -> dict:
    """Forward one tool call to its DoThesis endpoint as the calling user.

    The bearer goes through untouched, so the API applies its own auth,
    ownership checks, quota gates and credit debits. This server decides
    nothing — a tool that needed a decision of its own would be business logic
    the web app doesn't get, which is how the two surfaces drift apart.

    Async because a humanize is a 20-30s model round-trip: a blocking client
    here would pin the event loop and make one user's rewrite stall everyone
    else's tools/list.
    """
    path, body = tool.request(args)
    async with httpx.AsyncClient(
            timeout=float(os.getenv("DOTHESIS_MCP_TIMEOUT", "180"))) as client:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        # Tell the API which door this came through. Without it every connector
        # call is filed as a web run in `tool_runs`, and the admin view's whole
        # point — who is actually using each surface — reports one number for
        # two very different populations. Advisory only: the API defaults to
        # "web" and never trusts this for anything but labelling.
        headers["X-DoThesis-Surface"] = "mcp"
        r = await client.post(f"{API_URL}{path}", headers=headers, json=body)
    if r.status_code >= 400:
        # Surface the API's own structured error instead of an httpx traceback:
        # "insufficient_credit" or "already_running" is something the student
        # can act on, and the model can explain it.
        try:
            detail = r.json()
        except Exception:  # noqa: BLE001
            detail = {"message": r.text[:300]}
        raise ToolError(r.status_code, detail)
    return r.json()


class ToolError(Exception):
    def __init__(self, status: int, detail):
        self.status, self.detail = status, detail
        super().__init__(f"HTTP {status}: {detail}")


def _rpc_result(mid, result):
    return JSONResponse({"jsonrpc": "2.0", "id": mid, "result": result})


def _rpc_error(mid, code, message):
    return JSONResponse({"jsonrpc": "2.0", "id": mid,
                         "error": {"code": code, "message": message}})


def _unauthorized(request: Request, detail: str) -> Response:
    """401 carrying the pointer to our resource metadata.

    Without this header an MCP client has no way to learn WHERE to authenticate
    and falls back to probing the origin root — which is how Claude ended up
    POSTing dynamic client registration at the Next.js app and reporting
    "Couldn't register with dothesis's sign-in service".
    """
    base = oauth.base_url(request)
    return JSONResponse(
        {"error": "invalid_token", "error_description": detail},
        status_code=401,
        headers={"WWW-Authenticate":
                 f'Bearer realm="DoThesis", '
                 f'resource_metadata="{base}/.well-known/oauth-protected-resource/mcp"'})


def _caller(request: Request):
    """(token, user_id, client_id, error_response). The error is None on success.

    Identity comes back alongside the token because every tool call is audited
    by user + connector (audit.py); resolving it twice would mean decoding the
    JWT twice per request.
    """
    if not REQUIRE_AUTH:
        # Dev static-token path: there is no user to attribute calls to, so
        # nothing gets audited. See audit.record().
        return DEV_TOKEN, None, None, None
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None, None, None, _unauthorized(request, "missing Bearer token")
    token = auth.split(" ", 1)[1].strip()
    user_id, client_id = oauth.bearer_identity(token) if token else (None, None)
    if not user_id:
        return None, None, None, _unauthorized(request, "token is invalid or expired")
    return token, user_id, client_id, None


async def _audit(user_id, client_id, name, *, ok, error, started, args, out,
                 tool=None):
    """Write the audit row off the event loop. Never raises.

    In a threadpool because the INSERT is synchronous psycopg: blocking the loop
    on it would repeat the bug that made a single humanize stall every other
    caller's tools/list.

    The try/except is here as well as inside `audit.record` on purpose. Guarding
    only the INSERT leaves everything AROUND it — resolving the DSN, the
    threadpool hop, measuring the sizes — able to take down a call that had
    already succeeded. The tool result is the product; the audit row is
    bookkeeping, and bookkeeping does not get to veto the product.
    """
    try:
        await run_in_threadpool(
            audit.record,
            user_id=user_id, client_id=client_id, tool=name, ok=ok, error=error,
            duration_ms=int((time.monotonic() - started) * 1000),
            input_chars=_size(args),
            output_chars=len(tool.text_of(out)) if (tool and isinstance(out, dict)) else 0)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("mcp audit failed (tool=%s)", name)


def _size(args) -> int:
    """How much text the caller sent. Only the free-text fields count — an id
    argument is not volume, and counting it would make list_projects look as
    heavy as a humanize in the admin view."""
    a = args or {}
    return sum(len(str(a.get(k) or "")) for k in ("text", "reference", "topic"))


async def mcp_endpoint(request: Request):
    if request.method == "GET":
        # No server-initiated stream in this minimal build.
        return Response(status_code=405)
    token, user_id, client_id, err = _caller(request)
    if err:
        return err
    msg = await request.json()
    method, mid = msg.get("method"), msg.get("id")

    if method == "initialize":
        pv = (msg.get("params") or {}).get("protocolVersion", DEFAULT_PROTOCOL)
        return _rpc_result(mid, {
            "protocolVersion": pv,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "DoThesis", "version": "0.1.0"}})
    if method in ("notifications/initialized", "initialized"):
        return Response(status_code=202)
    if method == "ping":
        return _rpc_result(mid, {})
    if method == "tools/list":
        return _rpc_result(mid, {"tools": toolreg.as_mcp_schema()})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        tool = toolreg.BY_NAME.get(name)
        if tool is None:
            return _rpc_error(mid, -32602, f"unknown tool: {name}")
        args = params.get("arguments") or {}
        started = time.monotonic()

        # Rate limit BEFORE the work, and record the refusal — a throttled user
        # asking "why did nothing happen?" should be answerable from
        # /admin/connectors like every other outcome.
        try:
            await run_in_threadpool(ratelimit.check, user_id,
                                    toolreg.TIERS[tool.tier], tool.tier)
        except ratelimit.RateLimited as e:
            await _audit(user_id, client_id, name, ok=False, error="rate_limited",
                         started=started, args=args, out=None, tool=tool)
            return _rpc_result(mid, {
                "content": [{"type": "text", "text": str(e)}], "isError": True})

        # Audited on BOTH paths. A connector that throws for one user is exactly
        # what the log exists to surface, so a success-only record would hide
        # the interesting half.
        try:
            out = await _call_tool(tool, args, token)
        except ToolError as e:
            await _audit(user_id, client_id, name, ok=False,
                         error=f"http_{e.status}", started=started, args=args,
                         out=None, tool=tool)
            return _rpc_result(mid, {
                "content": [{"type": "text",
                             "text": json.dumps(e.detail, ensure_ascii=False)}],
                "isError": True})
        except Exception as e:  # noqa: BLE001 — surface upstream failure to the client
            await _audit(user_id, client_id, name, ok=False, error=str(e),
                         started=started, args=args, out=None, tool=tool)
            return _rpc_result(mid, {
                "content": [{"type": "text", "text": f"{name} call failed: {e}"}],
                "isError": True})

        # A dict with `ok=false` is the tool DECLINING (no_anchor,
        # frozen_violation) -- a real outcome, not a transport error, and the one
        # an admin most often has to explain to a student. Tools that return a
        # list (list_projects) have no such field and are always successes.
        failed = isinstance(out, dict) and bool(out.get("error"))
        await _audit(user_id, client_id, name, ok=not failed,
                     error=(out.get("error") if isinstance(out, dict) else None),
                     started=started, args=args, out=out, tool=tool)
        result = {
            "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
            "isError": failed,
        }
        # structuredContent must be an object per the MCP schema; list-returning
        # tools ship their payload in `content` only.
        if isinstance(out, dict):
            result["structuredContent"] = out
        return _rpc_result(mid, result)
    return _rpc_error(mid, -32601, f"method not found: {method}")


app = Starlette(routes=[
    Route("/mcp", mcp_endpoint, methods=["GET", "POST"]),
    # Discovery + the OAuth endpoints. These live at the ORIGIN ROOT, not under
    # /mcp, because that is where clients look for them — which is why the proxy
    # has to route `/.well-known/oauth-*` and `/oauth/*` here too and not to the
    # web app (deploy/nginx/dothesis.conf, RUNBOOK §5).
    *oauth.routes(),
])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,
                host=os.getenv("DOTHESIS_MCP_HOST", "127.0.0.1"),
                port=int(os.getenv("DOTHESIS_MCP_PORT", "9000")))

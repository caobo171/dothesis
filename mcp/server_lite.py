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

API_URL = os.getenv("DOTHESIS_API_URL", "http://localhost:7100").rstrip("/")
DEFAULT_PROTOCOL = "2025-06-18"

# The pre-OAuth escape hatch: one static token acting as one real user. It is
# now OFF unless explicitly asked for, and it was never safe to expose — see the
# "DEV ONLY, NOT SECURE YET" note this replaces in README.md. Setting
# DOTHESIS_MCP_REQUIRE_AUTH=0 on a public host hands that user's account to
# anyone who finds the URL.
REQUIRE_AUTH = os.getenv("DOTHESIS_MCP_REQUIRE_AUTH", "1") != "0"
DEV_TOKEN = os.getenv("DOTHESIS_ACCESS_TOKEN", "")

TOOLS = [{
    "name": "humanize",
    "description": (
        "Re-voice already-written academic prose so it reads less AI-generated, "
        "while freezing every number, table reference, term and citation (a rewrite "
        "that changes one is discarded and the original returned). Reduces the "
        "AI-detection smell; it is NOT a plagiarism/similarity tool and does NOT "
        "guarantee passing any detector. Work section by section."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Passage to re-voice."},
            "user_anchor": {"type": "string", "description":
                            "~150 words the USER wrote themselves; required if the "
                            "result is error='no_anchor'. Never fabricate it."},
            "language": {"type": "string", "default": "vi"},
        },
        "required": ["text"],
    },
}]


async def _call_humanize(args: dict, token: str) -> dict:
    """Forward the caller's own token so the humanize runs as the caller.

    Async because a humanize is a 20-30s Gemini round-trip. The previous
    blocking `httpx.post` inside an `async def` handler pinned the event loop
    for its whole duration, so a second user's `tools/list` would sit behind a
    stranger's rewrite. Harmless with one shared dev token; not harmless once
    the endpoint is public and per-user.
    """
    async with httpx.AsyncClient(
            timeout=float(os.getenv("DOTHESIS_MCP_TIMEOUT", "180"))) as client:
        r = await client.post(
            f"{API_URL}/api/v1/humanize",
            headers={"Authorization": f"Bearer {token}"} if token else {},
            json={"text": args.get("text", ""),
                  "user_anchor": args.get("user_anchor"),
                  "language": args.get("language", "vi")})
    r.raise_for_status()
    return r.json()


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


async def _audit(user_id, client_id, tool, *, ok, error, started, args, out):
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
            user_id=user_id, client_id=client_id, tool=tool, ok=ok, error=error,
            duration_ms=int((time.monotonic() - started) * 1000),
            input_chars=len(str((args or {}).get("text") or "")),
            output_chars=len(str((out or {}).get("text") or "")))
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("mcp audit failed (tool=%s)", tool)


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
        return _rpc_result(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        if params.get("name") != "humanize":
            return _rpc_error(mid, -32602, f"unknown tool: {params.get('name')}")
        args = params.get("arguments") or {}
        started = time.monotonic()
        # Audited on BOTH paths. A connector that throws for one user is exactly
        # what the log exists to surface, so a success-only record would hide
        # the interesting half.
        try:
            out = await _call_humanize(args, token)
        except Exception as e:  # noqa: BLE001 — surface upstream failure to the client
            await _audit(user_id, client_id, "humanize", ok=False, error=str(e),
                         started=started, args=args, out=None)
            return _rpc_result(mid, {
                "content": [{"type": "text", "text": f"humanize call failed: {e}"}],
                "isError": True})
        # `ok=false` inside a 200 is the tool declining (no_anchor,
        # frozen_violation) -- a real outcome, not a transport error, and the
        # one an admin most often needs to explain to a student.
        await _audit(user_id, client_id, "humanize", ok=not out.get("error"),
                     error=out.get("error"), started=started, args=args, out=out)
        return _rpc_result(mid, {
            "content": [{"type": "text",
                         "text": json.dumps(out, ensure_ascii=False)}],
            "structuredContent": out,
            "isError": bool(out.get("error"))})
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

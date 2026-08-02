"""DoThesis MCP server — SDK-free (Starlette only), for hosts where the MCP SDK
isn't installable (offline pip index) or where sharing DoThesis's venv must not
pull the SDK's pydantic>=2.12.

Implements the minimum of the Streamable-HTTP MCP protocol needed to expose the
`humanize` tool: `initialize`, `notifications/initialized`, `tools/list`,
`tools/call`, `ping`. Responses are plain JSON (the spec permits a JSON response
when the server doesn't stream). Good enough to validate the tunnel + tool over
a public URL; the fastmcp-based `server.py` + OAuth façade is the production path
for Claude's connector.

Run (DoThesis venv has starlette+uvicorn+httpx):
    export DOTHESIS_API_URL=http://localhost:7100
    export DOTHESIS_ACCESS_TOKEN=<dev user token>   # phase-1 only
    ../.venv/bin/python server_lite.py              # 127.0.0.1:9000/mcp
"""
from __future__ import annotations

import json
import os

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

API_URL = os.getenv("DOTHESIS_API_URL", "http://localhost:7100").rstrip("/")
DEV_TOKEN = os.getenv("DOTHESIS_ACCESS_TOKEN", "")
DEFAULT_PROTOCOL = "2025-06-18"

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


def _call_humanize(args: dict) -> dict:
    headers = {"Authorization": f"Bearer {DEV_TOKEN}"} if DEV_TOKEN else {}
    r = httpx.post(
        f"{API_URL}/api/v1/humanize",
        headers=headers,
        json={"text": args.get("text", ""),
              "user_anchor": args.get("user_anchor"),
              "language": args.get("language", "vi")},
        timeout=float(os.getenv("DOTHESIS_MCP_TIMEOUT", "180")),
    )
    r.raise_for_status()
    return r.json()


def _rpc_result(mid, result):
    return JSONResponse({"jsonrpc": "2.0", "id": mid, "result": result})


def _rpc_error(mid, code, message):
    return JSONResponse({"jsonrpc": "2.0", "id": mid,
                         "error": {"code": code, "message": message}})


async def mcp_endpoint(request: Request):
    if request.method == "GET":
        # No server-initiated stream in this minimal build.
        return Response(status_code=405)
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
        try:
            out = _call_humanize(params.get("arguments") or {})
        except Exception as e:  # noqa: BLE001 — surface upstream failure to the client
            return _rpc_result(mid, {
                "content": [{"type": "text", "text": f"humanize call failed: {e}"}],
                "isError": True})
        return _rpc_result(mid, {
            "content": [{"type": "text",
                         "text": json.dumps(out, ensure_ascii=False)}],
            "structuredContent": out,
            "isError": bool(out.get("error"))})
    return _rpc_error(mid, -32601, f"method not found: {method}")


app = Starlette(routes=[Route("/mcp", mcp_endpoint, methods=["GET", "POST"])])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,
                host=os.getenv("DOTHESIS_MCP_HOST", "127.0.0.1"),
                port=int(os.getenv("DOTHESIS_MCP_PORT", "9000")))

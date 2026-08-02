"""DoThesis MCP server (phase 1) — exposes `humanize` over MCP for Claude.

Thin adapter by design: the tool forwards to the DoThesis API
`POST /api/v1/humanize`, so all the real work (anchor selection, frozen-token
verification, the detector loop, model routing) runs inside DoThesis with its
own dependencies. This process stays tiny and is deployed as a SEPARATE service
(its own venv) — never share DoThesis's venv (the MCP SDK bumps pydantic and
would break thesis-stats).

Run (local dev):
    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    export DOTHESIS_API_URL=http://localhost:7100
    export DOTHESIS_ACCESS_TOKEN=<a dev user's access token>   # phase-1 only
    .venv/bin/python server.py            # Streamable-HTTP on 127.0.0.1:9000

Public (phase 2): front with HTTPS on your domain + the OAuth 2.1 façade
(see MCP_OAUTH_PLAN.md), which replaces the static DOTHESIS_ACCESS_TOKEN with a
per-user token minted from Claude's OAuth handshake against DoThesis's existing
Google login.
"""
from __future__ import annotations

import os

import httpx
from fastmcp import FastMCP

API_URL = os.getenv("DOTHESIS_API_URL", "http://localhost:7100").rstrip("/")
# Phase-1 local dev only. Phase-2 replaces this with the caller's OAuth token.
DEV_TOKEN = os.getenv("DOTHESIS_ACCESS_TOKEN", "")

mcp = FastMCP("DoThesis")


@mcp.tool
def humanize(text: str, user_anchor: str | None = None, language: str = "vi") -> dict:
    """Re-voice already-written academic prose so it reads less AI-generated,
    while freezing every number, table reference, term and citation (a rewrite
    that changes one is discarded and the original returned).

    This reduces the AI-detection "smell". It is NOT a plagiarism / similarity
    tool and does NOT guarantee passing any specific detector.

    Args:
        text: the passage to re-voice. Work section by section, not a whole thesis.
        user_anchor: ~150 words the USER wrote themselves. Required if the server
            replies error="no_anchor". Never fabricate this — a made-up anchor
            makes results worse.
        language: "vi" (default) or "en".

    Returns the DoThesis result: {ok, text, changed, error, hint, frozen_ok, ...}.
    On error="no_anchor", ask the user for their own ~150 words and retry.
    On error="frozen_violation", the original was kept — say so; do not claim it
    was humanized.
    """
    headers = {"Authorization": f"Bearer {DEV_TOKEN}"} if DEV_TOKEN else {}
    resp = httpx.post(
        f"{API_URL}/api/v1/humanize",
        headers=headers,
        json={"text": text, "user_anchor": user_anchor, "language": language},
        timeout=float(os.getenv("DOTHESIS_MCP_TIMEOUT", "180")),
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    mcp.run(
        transport=os.getenv("DOTHESIS_MCP_TRANSPORT", "http"),
        host=os.getenv("DOTHESIS_MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("DOTHESIS_MCP_PORT", "9000")),
    )

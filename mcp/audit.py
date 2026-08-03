"""Record every MCP tool call to `mcp_tool_calls`.

The uvicorn access log the MCP process already produces says `POST /mcp 200` and
nothing more — not who called, not which tool, not whether the tool itself
returned an error inside a 200 response. This module is what makes connector
usage answerable: who used it, how often, how heavy, and did it work.

TWO RULES THIS FILE OBEYS
-------------------------
1. **Recording must never break the call.** Every failure here is swallowed and
   logged. A student's humanize does not fail because the audit INSERT hit a
   dead connection — the tool result is the product, the audit row is
   bookkeeping, and the bookkeeping does not get to veto the product.

2. **Sizes, never prose.** `input_chars` / `output_chars` only. An audit log
   that quietly becomes a copy of everyone's thesis drafts is a liability you
   have to defend later. Sizes answer the operational questions without holding
   the content.

Like `oauth.py`, this writes DoThesis's Postgres with plain psycopg and imports
nothing from `app.*` — so the SQL here must be kept in step with the
`McpToolCall` model in `api/app/models.py`.
"""
from __future__ import annotations

import logging

import psycopg

from oauth import _dsn  # same connection-string handling, one place to fix it

log = logging.getLogger(__name__)


def record(*, user_id: str | None, client_id: str | None, tool: str, ok: bool,
           error: str | None, duration_ms: int,
           input_chars: int, output_chars: int) -> None:
    """Append one row. Never raises.

    `user_id` is None when auth is disabled (the dev static-token path), and
    there is no user to attribute the call to — nothing is recorded rather than
    inventing an owner, because a row with a fabricated user is worse than a
    missing one in exactly the audit the table exists for.
    """
    if not user_id:
        return
    try:
        with psycopg.connect(_dsn(), connect_timeout=5) as conn:
            conn.execute(
                "INSERT INTO mcp_tool_calls (user_id, client_id, tool, ok, error, "
                "duration_ms, input_chars, output_chars) "
                "VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, client_id, tool, ok, (error or None)[:500] if error else None,
                 duration_ms, input_chars, output_chars))
    except Exception:  # noqa: BLE001 — see rule 1 above
        log.exception("mcp audit write failed (tool=%s user=%s)", tool, user_id)

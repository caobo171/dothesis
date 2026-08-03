"""Admin view of MCP connector usage — who connected, and what they called.

Answers the two questions the uvicorn access log cannot: which users have a live
connector grant, and what has actually been invoked through it. Reads
`mcp_oauth_*` (written by mcp/oauth.py) and `mcp_tool_calls` (written by
mcp/audit.py).

Read-only by design. Revoking someone else's grant from here is a bigger
decision than a debugging view should carry — a user can already disconnect
their own via /connectors/revoke, and an admin doing it silently to a student
mid-thesis is the kind of action that wants an explicit ask first.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, case, cast, desc, func, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..jwt_auth import AuthedBody
from ..models import McpOAuthClient, McpOAuthRefreshToken, McpToolCall, User

router = APIRouter(prefix="/admin/connectors", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class CallsBody(AuthedBody):
    page: int = 1
    page_size: int = 25
    # Optional filters. `ok=False` alone is the useful one — "show me what's
    # failing" is the reason an admin opens this page at all.
    user_id: uuid.UUID | None = None
    tool: str | None = None
    ok: bool | None = None


@router.post("/calls")
def list_calls(body: CallsBody, db: Session = Depends(db_session)):
    page = max(1, body.page)
    size = min(max(1, body.page_size), 200)

    stmt = (
        select(McpToolCall, User.email)
        .join(User, User.id == McpToolCall.user_id)
    )
    if body.user_id:
        stmt = stmt.where(McpToolCall.user_id == body.user_id)
    if body.tool:
        stmt = stmt.where(McpToolCall.tool == body.tool)
    if body.ok is not None:
        stmt = stmt.where(McpToolCall.ok.is_(body.ok))

    total = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0

    rows = db.execute(
        stmt.order_by(desc(McpToolCall.created_at))
            .offset((page - 1) * size).limit(size)
    ).all()

    return {
        "items": [{
            "id": str(c.id),
            "user_email": email,
            "user_id": str(c.user_id),
            "client_id": c.client_id,
            "tool": c.tool,
            "ok": c.ok,
            "error": c.error,
            "duration_ms": c.duration_ms,
            "input_chars": c.input_chars,
            "output_chars": c.output_chars,
            "created_at": c.created_at.isoformat(),
        } for c, email in rows],
        "total": total,
        "page": page,
        "page_size": size,
    }


@router.post("/summary")
def usage_summary(body: AuthedBody, db: Session = Depends(db_session)):
    """Per-user totals plus the live grants — the campaign-metrics view.

    Grants and calls are counted separately and then merged, because they answer
    different questions and a user can legitimately appear in one and not the
    other: connected but never used it (the interesting drop-off for the
    giveaway), or used it and since disconnected (still in the usage history).
    """
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)

    usage = db.execute(
        select(
            McpToolCall.user_id,
            User.email,
            func.count().label("calls"),
            func.sum(cast(case((McpToolCall.ok.is_(False), 1), else_=0), Integer)).label("failed"),
            func.sum(cast(McpToolCall.input_chars, Integer)).label("input_chars"),
            func.max(McpToolCall.created_at).label("last_call"),
            func.sum(cast(case((McpToolCall.created_at >= day_ago, 1), else_=0), Integer)).label("calls_24h"),
        )
        .join(User, User.id == McpToolCall.user_id)
        .group_by(McpToolCall.user_id, User.email)
        .order_by(desc(func.count()))
    ).all()

    grants = db.execute(
        select(User.email, McpOAuthClient.client_name,
               func.min(McpOAuthRefreshToken.created_at))
        .join(McpOAuthRefreshToken, McpOAuthRefreshToken.user_id == User.id)
        .join(McpOAuthClient,
              McpOAuthClient.client_id == McpOAuthRefreshToken.client_id)
        .where(McpOAuthRefreshToken.revoked.is_(False),
               McpOAuthRefreshToken.expires_at > now)
        .group_by(User.email, McpOAuthClient.client_name)
    ).all()

    return {
        "users": [{
            "user_id": str(u.user_id),
            "user_email": u.email,
            "calls": u.calls,
            "failed": u.failed or 0,
            "input_chars": u.input_chars or 0,
            "calls_24h": u.calls_24h or 0,
            "last_call": u.last_call.isoformat() if u.last_call else None,
        } for u in usage],
        "grants": [{
            "user_email": email,
            "client_name": name,
            "connected_at": since.isoformat(),
        } for email, name, since in grants],
        "totals": {
            "calls": sum(u.calls for u in usage),
            "users_with_calls": len(usage),
            "live_grants": len(grants),
        },
    }

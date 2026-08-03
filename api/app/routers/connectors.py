"""Connected AI apps — what the student granted, and how to take it back.

These endpoints exist because the MCP OAuth grants live in DoThesis's own
database (mcp/oauth.py, migration 20260803_mcpoauth01). While they sat in a
SQLite file next to the MCP process, the honest thing the /connect page could
say was "remove the connector in your AI client" — DoThesis could not see a
grant, let alone end one. Now it can.

Revocation here is deliberately server-side-only: it kills the refresh tokens,
and the 1-hour access token then expires on its own. We do NOT try to reach into
the AI client and delete anything — we can't, and pretending otherwise would be
the dishonest version of a "Disconnect" button. The user-visible promise is
"within the hour", which is what the response says.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..jwt_auth import AuthedBody
from ..models import McpOAuthClient, McpOAuthCode, McpOAuthRefreshToken, User

router = APIRouter(prefix="/connectors", tags=["connectors"])


class RevokeBody(AuthedBody):
    client_id: str


@router.post("/list")
def list_connectors(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """The AI clients this user has an active grant with.

    Grouped by client, because a client legitimately holds several refresh
    tokens over time: every refresh rotates one out and a new one in, and the
    retired rows stay until the expiry sweep. Listing rows would show one
    "connection" per refresh, which is nonsense to a reader.
    """
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(
            McpOAuthClient.client_id,
            McpOAuthClient.client_name,
            McpOAuthRefreshToken.created_at,
            McpOAuthRefreshToken.expires_at,
        )
        .join(McpOAuthRefreshToken,
              McpOAuthRefreshToken.client_id == McpOAuthClient.client_id)
        .where(
            McpOAuthRefreshToken.user_id == user.id,
            McpOAuthRefreshToken.revoked.is_(False),
            McpOAuthRefreshToken.expires_at > now,
        )
        .order_by(McpOAuthRefreshToken.created_at.desc())
    ).all()

    by_client: dict[str, dict] = {}
    for client_id, client_name, created_at, expires_at in rows:
        entry = by_client.get(client_id)
        if entry is None:
            # First row wins for "connected_at" only because of the DESC order
            # above — so overwrite it downward as older rows arrive.
            by_client[client_id] = {
                "client_id": client_id,
                "client_name": client_name,
                "connected_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
        else:
            if created_at.isoformat() < entry["connected_at"]:
                entry["connected_at"] = created_at.isoformat()
            if expires_at.isoformat() > entry["expires_at"]:
                entry["expires_at"] = expires_at.isoformat()

    return {"connectors": list(by_client.values())}


@router.post("/revoke")
def revoke_connector(
    body: RevokeBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """End this user's grant to one client.

    Scoped to `user.id` in the WHERE clause, not just checked beforehand: the
    client_id is caller-supplied and is shared across every user of that AI
    client (Claude registers once per workspace). A revoke that matched on
    client_id alone would disconnect strangers.
    """
    revoked = db.execute(
        update(McpOAuthRefreshToken)
        .where(
            McpOAuthRefreshToken.user_id == user.id,
            McpOAuthRefreshToken.client_id == body.client_id,
            McpOAuthRefreshToken.revoked.is_(False),
        )
        .values(revoked=True)
    ).rowcount

    # Any unredeemed code for this pair would still be exchangeable for a fresh
    # token, which would undo the revoke seconds after it happened.
    db.execute(
        delete(McpOAuthCode).where(
            McpOAuthCode.user_id == user.id,
            McpOAuthCode.client_id == body.client_id,
        )
    )
    db.commit()

    return {
        "revoked": revoked,
        # Said plainly so the UI doesn't have to invent a reassuring phrasing:
        # already-issued access tokens are stateless JWTs and stay valid until
        # they expire. Nothing can recall them.
        "detail": "Refresh access ended. Any token already issued stops working within the hour.",
    }

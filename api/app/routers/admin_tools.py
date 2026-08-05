"""Admin view of standalone tool usage — who ran what, and what it cost.

The tools (humanize, cite a .docx, check a reference list, writing rhythm) are
the one surface with no project, no job and no thread behind it, so nothing in
admin/jobs or admin/papers ever showed them. Reads `tool_runs`, written by
app/tool_billing.py.

The number this page exists for is the GAP: `credits_cost` vs
`credits_charged`. Charging is capped at the balance, so a student at zero is
under-billed rather than refused — a deliberate trade, but one that is only
defensible while somebody can see how much it adds up to.

Read-only, like admin/connectors. Adjusting someone's balance from a usage
report is a bigger decision than a reporting view should carry.
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
from ..models import ToolRun, User

router = APIRouter(prefix="/admin/tools", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class RunsBody(AuthedBody):
    page: int = 1
    page_size: int = 25
    user_id: uuid.UUID | None = None
    tool: str | None = None
    ok: bool | None = None
    # "Show me what ran for free" — the under-billing view, which is the reason
    # both credit columns are stored.
    unpaid_only: bool = False


@router.post("/runs")
def list_runs(body: RunsBody, db: Session = Depends(db_session)):
    page = max(1, body.page)
    size = min(max(1, body.page_size), 200)

    stmt = select(ToolRun, User.email).join(User, User.id == ToolRun.user_id)
    if body.user_id:
        stmt = stmt.where(ToolRun.user_id == body.user_id)
    if body.tool:
        stmt = stmt.where(ToolRun.tool == body.tool)
    if body.ok is not None:
        stmt = stmt.where(ToolRun.ok.is_(body.ok))
    if body.unpaid_only:
        stmt = stmt.where(ToolRun.credits_charged < ToolRun.credits_cost)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(desc(ToolRun.created_at))
            .offset((page - 1) * size).limit(size)
    ).all()

    return {
        "items": [{
            "id": str(r.id),
            "user_email": email,
            "user_id": str(r.user_id),
            "surface": r.surface,
            "tool": r.tool,
            "ok": r.ok,
            "error": r.error,
            "units": r.units,
            "credits_cost": r.credits_cost,
            "credits_charged": r.credits_charged,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat(),
        } for r, email in rows],
        "total": total,
        "page": page,
        "page_size": size,
    }


@router.post("/summary")
def usage_summary(body: AuthedBody, db: Session = Depends(db_session)):
    """Per-tool and per-user rollups, plus the 24h slice.

    Grouped BY TOOL first because that is the product question — which of these
    is anyone actually using, and is it paying for itself. The per-user table
    underneath answers the abuse question.
    """
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)

    def _sum(col):
        return func.coalesce(func.sum(cast(col, Integer)), 0)

    by_tool = db.execute(
        select(
            ToolRun.tool,
            func.count().label("runs"),
            _sum(case((ToolRun.ok.is_(False), 1), else_=0)).label("failed"),
            _sum(ToolRun.units).label("units"),
            _sum(ToolRun.credits_cost).label("cost"),
            _sum(ToolRun.credits_charged).label("charged"),
            _sum(ToolRun.prompt_tokens + ToolRun.completion_tokens).label("tokens"),
            _sum(case((ToolRun.created_at >= day_ago, 1), else_=0)).label("runs_24h"),
            func.count(func.distinct(ToolRun.user_id)).label("users"),
            func.max(ToolRun.created_at).label("last_run"),
        )
        .group_by(ToolRun.tool)
        .order_by(desc(func.count()))
    ).all()

    by_user = db.execute(
        select(
            ToolRun.user_id,
            User.email,
            func.count().label("runs"),
            _sum(ToolRun.credits_cost).label("cost"),
            _sum(ToolRun.credits_charged).label("charged"),
            _sum(case((ToolRun.created_at >= day_ago, 1), else_=0)).label("runs_24h"),
            func.max(ToolRun.created_at).label("last_run"),
        )
        .join(User, User.id == ToolRun.user_id)
        .group_by(ToolRun.user_id, User.email)
        .order_by(desc(func.count()))
        .limit(100)
    ).all()

    return {
        "tools": [{
            "tool": t.tool,
            "runs": t.runs,
            "failed": t.failed,
            "units": t.units,
            "credits_cost": t.cost,
            "credits_charged": t.charged,
            "tokens": t.tokens,
            "runs_24h": t.runs_24h,
            "users": t.users,
            "last_run": t.last_run.isoformat() if t.last_run else None,
        } for t in by_tool],
        "users": [{
            "user_id": str(u.user_id),
            "user_email": u.email,
            "runs": u.runs,
            "credits_cost": u.cost,
            "credits_charged": u.charged,
            "runs_24h": u.runs_24h,
            "last_run": u.last_run.isoformat() if u.last_run else None,
        } for u in by_user],
        "totals": {
            "runs": sum(t.runs for t in by_tool),
            "runs_24h": sum(t.runs_24h for t in by_tool),
            "credits_cost": sum(t.cost for t in by_tool),
            "credits_charged": sum(t.charged for t in by_tool),
            # What the balance cap gave away. The reason this page exists.
            "credits_uncollected": sum(t.cost - t.charged for t in by_tool),
        },
    }


@router.post("/pricing")
def pricing_table(_body: AuthedBody):
    """What each tool currently costs, straight from pricing.py.

    Surfaced because the rates were picked for shape rather than costed, and a
    price nobody can see from the admin panel is a price nobody revisits.
    """
    from ..pricing import TOOL_COST_FLAT, TOOL_COST_PER_UNIT, TOOL_FREE  # noqa: PLC0415

    return {
        "per_unit": TOOL_COST_PER_UNIT,
        "flat": TOOL_COST_FLAT,
        "free": sorted(TOOL_FREE),
        "note": "Tools that call a model are billed on tokens at each model's "
                "own rate and do not appear here.",
    }

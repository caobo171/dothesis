"""Humanize endpoint — re-voice academic prose while freezing every number,
table ref, term and citation. Powers the DoThesis MCP `humanize` tool (see
`mcp/`). Mounted under /api/v1 in the orchestrator-enabled block, because the
humanize pass lives in the orchestrator.

Honest contract (mirror it in any UI/marketing): this reduces the AI-detection
"smell" of the prose. It is NOT a plagiarism/similarity tool and does NOT
guarantee passing any specific detector. Numbers/tables/terms/citations are
frozen — a rewrite that alters one is discarded and the original returned.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import User
from ..tool_billing import Timer, record_tool_run, surface_of
from ..user_memory import load_user_prefs, write_user_prefs

logger = logging.getLogger(__name__)
router = APIRouter(tags=["humanize"])


class HumanizeIn(BaseModel):
    text: str = Field(min_length=1, description="Already-written passage to re-voice.")
    user_anchor: str | None = Field(
        default=None,
        description="~150 words the user wrote themselves; required when no "
                    "library anchor is installed for this language.")
    # None = detect it from `text`. A hard "vi" default here translated English
    # passages instead of re-voicing them (orchestrator.tools.humanize
    # .detect_language); it survives only as a hint for text too short to read.
    language: str | None = None


class HumanizeOut(BaseModel):
    ok: bool
    # What this call cost the caller, in credits. Returned so the MCP tool and
    # the web client can both show it without a second round-trip — a student
    # spending credits from a chat window has no other way to see the meter run.
    credits_charged: int = 0
    text: str
    changed: bool = False
    error: str | None = None
    hint: str | None = None
    anchor: str | None = None
    frozen_ok: bool | None = None
    score: float | None = None
    rounds: int | None = None


@router.post("/humanize", response_model=HumanizeOut)
def humanize_endpoint(
    request: Request,
    body: HumanizeIn,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> HumanizeOut:
    """Re-voice `body.text`. Auth: Bearer header or `access_token` in body.

    Returns the humanized text, or `ok=false` with an `error`:
    - `no_anchor`   → ask the user for ~150 of their own words, retry with `user_anchor`.
    - `frozen_violation` → a number/citation would have changed; original kept.
    """
    # Lazy import: the orchestrator package is only present/enabled in this block.
    from orchestrator.tools.humanize import humanize_prose  # noqa: PLC0415

    # Fall back to the caller's SAVED anchor. The shipped anchor library is
    # empty on purpose (an anchor must be off the LLM training distribution, so
    # it cannot be generated), so without this an MCP client that humanizes a
    # second passage gets no_anchor even though the user already supplied one.
    anchor = (body.user_anchor or "").strip()
    if not anchor:
        anchor = ((load_user_prefs(db, user.id) or {}).get("writing_anchor") or "").strip()

    with Timer() as timer:
        r = humanize_prose(body.text, language=body.language, user_anchor=anchor or None)

    # Persist only a caller-supplied anchor, and only once it worked — saving a
    # sample that produced no_anchor would pin the user to a bad anchor.
    if (body.user_anchor or "").strip() and r.get("ok"):
        try:
            write_user_prefs(db, user.id, {"writing_anchor": body.user_anchor.strip()})
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("humanize: anchor save failed for user %s", user.id)
    charged = record_tool_run(
        db, user, surface=surface_of(request), tool="humanize", ok=bool(r.get("ok")),
        error=r.get("error"), usage=r.get("usage") or [],
        duration_ms=timer.ms).charged

    frozen = r.get("frozen") or {}
    return HumanizeOut(
        credits_charged=charged,
        ok=bool(r.get("ok")),
        text=r.get("text", body.text),
        changed=bool(r.get("changed")),
        error=r.get("error"),
        hint=r.get("hint"),
        anchor=r.get("anchor"),
        frozen_ok=frozen.get("ok") if frozen else None,
        score=r.get("score"),
        rounds=r.get("rounds"),
    )

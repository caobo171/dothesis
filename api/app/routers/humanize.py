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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import current_user
from ..models import User

router = APIRouter(tags=["humanize"])


class HumanizeIn(BaseModel):
    text: str = Field(min_length=1, description="Already-written passage to re-voice.")
    user_anchor: str | None = Field(
        default=None,
        description="~150 words the user wrote themselves; required when no "
                    "library anchor is installed for this language.")
    language: str = "vi"


class HumanizeOut(BaseModel):
    ok: bool
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
    body: HumanizeIn,
    user: User = Depends(current_user),
) -> HumanizeOut:
    """Re-voice `body.text`. Auth: Bearer header or `access_token` in body.

    Returns the humanized text, or `ok=false` with an `error`:
    - `no_anchor`   → ask the user for ~150 of their own words, retry with `user_anchor`.
    - `frozen_violation` → a number/citation would have changed; original kept.
    """
    # Lazy import: the orchestrator package is only present/enabled in this block.
    from orchestrator.tools.humanize import humanize_prose  # noqa: PLC0415
    r = humanize_prose(
        body.text, language=body.language, user_anchor=(body.user_anchor or None))
    frozen = r.get("frozen") or {}
    return HumanizeOut(
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

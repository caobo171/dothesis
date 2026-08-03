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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import User
from ..user_memory import load_user_prefs, write_user_prefs

logger = logging.getLogger(__name__)
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


def _meter_and_charge(db: Session, user: User, usage: list[dict]) -> int:
    """Record the LLM cost in `token_ledger` and debit the caller.

    Until now humanize called the model directly, so it wrote no ledger row and
    charged nothing — a blind spot on the WEB path as much as over MCP. The
    tokens are real either way; only the accounting was missing.

    Billing follows job_runner._charge_auto_run exactly rather than inventing a
    second scheme: bill each ledger row at ITS OWN model's rate via
    `credit_multiplier`, because a pass can span models (the anchor router and
    the rewrite are separately configurable) and one scalar cannot price that.

    Charged AFTER the work and capped at the balance, again matching auto runs.
    That means a user at zero is under-billed rather than refused. The trade is
    deliberate: refusing here would fail a rewrite the student already waited
    30s for, and the under-charge is visible (logged, and in token_ledger)
    instead of silent. A hard pre-flight gate is a pricing decision, not a
    metering one.

    Never raises. A billing failure must not lose a rewrite that succeeded.
    """
    if not usage:
        return 0

    from ..credit_ledger import InsufficientCredit, debit  # noqa: PLC0415
    from ..models import TokenLedger  # noqa: PLC0415
    from ..pricing import credit_multiplier  # noqa: PLC0415

    # --- 1. METER. Always, and committed on its own. -----------------------
    # The tokens were spent whether or not we can bill for them, so the ledger
    # write must not share a transaction with the debit: an unbillable call
    # rolling back its own cost record is how a blind spot comes back.
    by_model: dict[str, int] = {}
    try:
        for u in usage:
            model = str(u.get("model") or "unknown")
            p_tok = int(u.get("prompt_tokens") or 0)
            c_tok = int(u.get("completion_tokens") or 0)
            db.add(TokenLedger(
                project_id=None, user_id=user.id, action_kind="humanize",
                model=model, prompt_tokens=p_tok, completion_tokens=c_tok,
                reserved=0, duration_ms=0))
            by_model[model] = by_model.get(model, 0) + p_tok + c_tok
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("humanize metering failed for user %s", user.id)
        db.rollback()
        return 0

    total = sum(by_model.values())
    if total <= 0:
        # The provider surfaced no usage metadata. The rows above still record
        # that the calls happened — "did we attempt N calls at $0 because the
        # provider stopped reporting?" is a question worth being able to answer.
        return 0

    # --- 2. BILL. Best-effort, never fatal. --------------------------------
    cost = max(1, round(sum(t / 1000 * credit_multiplier(m)
                            for m, t in by_model.items())))
    try:
        # Re-read the balance from the DB rather than trusting `user.credit`.
        # The User handed over by `current_user` was loaded at request start and
        # a 30s humanize is long enough for a concurrent charge to have moved it
        # — capping against the stale value made debit() raise
        # InsufficientCredit and (before the split above) took the ledger row
        # down with it.
        fresh = db.get(User, user.id)
        charge = min(cost, (fresh.credit if fresh else 0) or 0)
        if charge > 0:
            debit(db, fresh, delta=charge, reason="humanize",
                  ref_type="humanize", ref_id=None)
            db.commit()
        if charge < cost:
            logger.warning(
                "humanize under-billed user=%s: cost=%s charged=%s", user.id, cost, charge)
        return charge
    except InsufficientCredit:
        # Lost a race with another charge between the read and the lock. The
        # cost is already recorded; do not fail a rewrite over the invoice.
        logger.warning("humanize: balance raced to zero for user %s", user.id)
        db.rollback()
        return 0
    except Exception:  # noqa: BLE001
        logger.exception("humanize charge failed for user %s", user.id)
        db.rollback()
        return 0


@router.post("/humanize", response_model=HumanizeOut)
def humanize_endpoint(
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

    r = humanize_prose(body.text, language=body.language, user_anchor=anchor or None)

    # Persist only a caller-supplied anchor, and only once it worked — saving a
    # sample that produced no_anchor would pin the user to a bad anchor.
    if (body.user_anchor or "").strip() and r.get("ok"):
        try:
            write_user_prefs(db, user.id, {"writing_anchor": body.user_anchor.strip()})
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("humanize: anchor save failed for user %s", user.id)
    charged = _meter_and_charge(db, user, r.get("usage") or [])

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

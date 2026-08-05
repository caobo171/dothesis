"""One place where a standalone tool run is recorded and charged.

Before this, billing lived inside humanize's `_meter_and_charge` and every other
tool either borrowed it (and got stamped action_kind="humanize" whatever it
actually was) or charged nothing at all because it called no model and there
were no tokens to meter. Neither was decided; both fell out of billing being
wired to token usage.

So this is the single chokepoint for BOTH schemes:

  tokens — a tool that calls a model bills what the model cost, per model,
           via credit_multiplier. Unchanged behaviour, just moved.
  units  — a tool that calls no model bills a flat rate from pricing.py: per
           CrossRef lookup, or per run.

and it always writes a `tool_runs` row, whether the run succeeded, failed, or
charged nothing — a tool being used heavily for free is exactly what an audit
table is for.

THE ORDER MATTERS, and it is the same order humanize established:

  1. RECORD, committed on its own. The work happened whether or not it can be
     billed; a metering write that shares a transaction with the debit is how a
     failed charge silently erases the evidence it was ever incurred.
  2. CHARGE, best-effort, capped at the balance, never fatal. A student at zero
     is under-billed rather than refused. Refusing here would fail a document
     they already waited a minute for, and the under-charge is visible — logged,
     and in `tool_runs.credits_cost` vs `credits_charged` — instead of silent.

A hard pre-flight gate is a pricing decision, not a metering one, and belongs
above this function if it is ever wanted.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from .models import User

logger = logging.getLogger(__name__)


@dataclass
class ToolCharge:
    """What a run cost, and what was actually taken for it."""
    cost: int = 0
    charged: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usage: list[dict] = field(default_factory=list)

    @property
    def under_billed(self) -> bool:
        return self.charged < self.cost


def _token_cost(usage: list[dict]) -> tuple[int, dict[str, int]]:
    """Credits owed for a list of {model, prompt_tokens, completion_tokens}.

    Billed at EACH model's own rate rather than one blended scalar: a single run
    can span models (the anchor router and the rewrite are separately
    configurable) and one number cannot price that. Same rule as
    job_runner._charge_auto_run.
    """
    from .pricing import credit_multiplier  # noqa: PLC0415

    by_model: dict[str, int] = {}
    for u in usage:
        model = str(u.get("model") or "unknown")
        total = int(u.get("prompt_tokens") or 0) + int(u.get("completion_tokens") or 0)
        by_model[model] = by_model.get(model, 0) + total
    if not by_model or sum(by_model.values()) <= 0:
        return 0, by_model
    return max(1, round(sum(t / 1000 * credit_multiplier(m)
                            for m, t in by_model.items()))), by_model


def tool_cost(tool: str, *, units: int = 0, usage: list[dict] | None = None,
              ok: bool = True) -> int:
    """What this run should cost, before any balance cap.

    A FAILED run is not free, and the two halves of the price part ways here:

      tokens — always billed. Three humanize rounds that then fail the frozen
               gate cost us exactly what three that succeed cost; the model ran.
               Billing successes only would silently eat that, and
               test_a_failed_pass_is_still_billed exists to hold the line.
      units  — never billed on failure. A CrossRef timeout or an unconfigured
               similarity provider did no work for the student, and charging
               for a lookup that did not happen is indefensible.

    Public so a route can quote a price without also charging for it.
    """
    from .pricing import TOOL_COST_FLAT, TOOL_COST_PER_UNIT, TOOL_FREE  # noqa: PLC0415

    if tool in TOOL_FREE:
        return 0
    cost, _ = _token_cost(usage or [])
    if ok:
        cost += TOOL_COST_PER_UNIT.get(tool, 0) * max(0, units)
        cost += TOOL_COST_FLAT.get(tool, 0)
    return cost


def record_tool_run(
    db: Session,
    user: User,
    *,
    tool: str,
    ok: bool = True,
    error: str | None = None,
    units: int = 0,
    usage: list[dict] | None = None,
    duration_ms: int = 0,
    surface: str = "web",
) -> ToolCharge:
    """Record one tool run, meter its tokens, and debit the caller.

    Returns what was charged. NEVER raises: a billing failure must not lose work
    that already succeeded, and an audit row must not be the reason a student's
    document does not come back.
    """
    usage = usage or []
    result = ToolCharge(usage=usage)
    # One outer guard on top of the per-step ones below, so the "never raises"
    # above is a property of this function rather than a hope about its
    # helpers. Every caller is a route that has ALREADY done the work — losing
    # a student's rewritten document to a billing bug is the one outcome worth
    # writing a redundant try for.
    try:
        result.prompt_tokens = sum(int(u.get("prompt_tokens") or 0) for u in usage)
        result.completion_tokens = sum(int(u.get("completion_tokens") or 0) for u in usage)
        result.cost = tool_cost(tool, units=units, usage=usage, ok=ok)

        _meter(db, user, tool=tool, usage=usage)
        if result.cost > 0:
            result.charged = _charge(db, user, tool=tool, cost=result.cost)
        _write_run(db, user, tool=tool, ok=ok, error=error, units=units,
                   duration_ms=duration_ms, surface=surface, result=result)
    except Exception:  # noqa: BLE001
        logger.exception("tool accounting failed outright: tool=%s user=%s",
                         tool, getattr(user, "id", None))
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return result


def _meter(db: Session, user: User, *, tool: str, usage: list[dict]) -> None:
    """One `token_ledger` row per model, committed on its own.

    `action_kind` is the TOOL, not "humanize" — which is what every row said
    before, including the ones written by the citation walk, making the per-
    action cost table the ledger exists for unreadable.
    """
    if not usage:
        return
    from .models import TokenLedger  # noqa: PLC0415

    try:
        for u in usage:
            db.add(TokenLedger(
                project_id=None, user_id=user.id, action_kind=tool,
                model=str(u.get("model") or "unknown"),
                prompt_tokens=int(u.get("prompt_tokens") or 0),
                completion_tokens=int(u.get("completion_tokens") or 0),
                reserved=0, duration_ms=0))
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("tool metering failed: tool=%s user=%s", tool, user.id)
        db.rollback()


def _charge(db: Session, user: User, *, tool: str, cost: int) -> int:
    """Debit up to `cost`, capped at the live balance. Returns what was taken."""
    from .credit_ledger import InsufficientCredit, debit  # noqa: PLC0415

    try:
        # Re-read the balance rather than trusting `user.credit`: the User handed
        # over by `current_user` was loaded at request start, and a minute-long
        # document run is long enough for a concurrent charge to have moved it.
        fresh = db.get(User, user.id)
        charge = min(cost, (fresh.credit if fresh else 0) or 0)
        if charge <= 0:
            logger.warning("tool %s: no balance to charge user=%s cost=%s",
                           tool, user.id, cost)
            return 0
        debit(db, fresh, delta=charge, reason=tool, ref_type="tool", ref_id=None)
        db.commit()
        if charge < cost:
            logger.warning("tool %s under-billed user=%s cost=%s charged=%s",
                           tool, user.id, cost, charge)
        return charge
    except InsufficientCredit:
        # Lost a race between the read and the lock. The cost is recorded; do
        # not fail the run over the invoice.
        logger.warning("tool %s: balance raced to zero for user %s", tool, user.id)
        db.rollback()
        return 0
    except Exception:  # noqa: BLE001
        logger.exception("tool %s charge failed for user %s", tool, user.id)
        db.rollback()
        return 0


def _write_run(db: Session, user: User, *, tool: str, ok: bool, error: str | None,
               units: int, duration_ms: int, surface: str,
               result: ToolCharge) -> None:
    from .models import ToolRun  # noqa: PLC0415

    try:
        db.add(ToolRun(
            user_id=user.id, surface=surface, tool=tool, ok=ok,
            error=(error or None), units=max(0, units),
            credits_cost=result.cost, credits_charged=result.charged,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            duration_ms=max(0, duration_ms)))
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("tool_runs write failed: tool=%s user=%s", tool, user.id)
        db.rollback()


# Surfaces we will file a run under. An unknown value is recorded as "web"
# rather than stored: the header is set by whatever called us, and an audit
# column that echoes arbitrary caller-supplied text is not an audit column.
_SURFACES = frozenset({"web", "mcp", "api"})


def surface_of(request) -> str:
    """Which door this call came through, from the X-DoThesis-Surface header.

    Advisory and unauthenticated ON PURPOSE. It labels a row for a usage report;
    nothing is billed, gated or granted differently because of it, so a caller
    lying about it gains nothing. Anything not in the allowlist is "web".
    """
    try:
        value = (request.headers.get("x-dothesis-surface") or "").strip().lower()
    except Exception:  # noqa: BLE001
        return "web"
    return value if value in _SURFACES else "web"


class Timer:
    """Wall time for a run, in ms. `with Timer() as t: ...` then `t.ms`."""

    def __init__(self) -> None:
        self.ms = 0
        self._start = 0.0

    def __enter__(self) -> Timer:
        import time  # noqa: PLC0415
        self._start = time.monotonic()
        return self

    def __exit__(self, *_exc: Any) -> None:
        import time  # noqa: PLC0415
        self.ms = int((time.monotonic() - self._start) * 1000)

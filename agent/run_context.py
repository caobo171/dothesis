"""Run-scoped hints for a single headless run.

`report_chapters` is a ContextVar (not a global → isolated per run, thread-safe)
holding the chapters a PARTNER actually ordered. The headless entrypoint sets it
from the resolved order; the M5 agent reads it to compose ONLY those chapters
instead of the whole 6-chapter thesis. Unset (the interactive/chat default, or
if it doesn't propagate) → compose everything, so reading it is always safe.
"""
from __future__ import annotations

import contextvars
import os

report_chapters: contextvars.ContextVar[tuple[str, ...] | None] = contextvars.ContextVar(
    "report_chapters", default=None
)

# A headless run is ONE report per subprocess, so a process-global env var is a
# safe, thread/async-proof carrier — the ContextVar alone does NOT survive the
# executor threads LangGraph runs sync tool nodes in. We set both and read
# whichever is populated.
_ENV_KEY = "DOTHESIS_REPORT_CHAPTERS"

# Report-only: tell the backfill's M2 reconstruction to run a REAL literature
# search (deep scout + domain supplement) instead of pure LLM recall, so report
# citations carry real DOIs. Same subprocess-scoped env carrier as the chapters
# hint. Interactive chat backfill never sets this → stays fast.
_GROUND_M2_KEY = "DOTHESIS_BACKFILL_GROUND_M2"


def set_report_chapters(chapters) -> None:
    """Set the ordered-chapters hint for the current run (no-op on empty)."""
    if chapters:
        report_chapters.set(tuple(chapters))
        os.environ[_ENV_KEY] = ",".join(str(c) for c in chapters)


def set_grounded_backfill() -> None:
    """Report-only opt-in: backfill's M2 runs a real literature search."""
    os.environ[_GROUND_M2_KEY] = "1"


def _current_scope() -> tuple[str, ...] | None:
    scope = report_chapters.get()
    if scope:
        return scope
    raw = os.environ.get(_ENV_KEY)
    if raw:
        return tuple(c for c in raw.split(",") if c)
    return None


def required_modules() -> frozenset[str] | None:
    """The modules THIS run must finish, derived from the ordered chapters — the
    same fact RunProfile.required_modules carries, but reachable from the agent's
    per-turn roadmap steering (which has no RunProfile in hand). None when no
    partner scope is set (interactive chat) → the roadmap keeps all five modules.

    This is what lets the [NEXT] header skip a module the order doesn't need: a
    3-chapter {intro, lit_review, methodology} order needs {M2, M3, M5}, so the
    agent must NOT be steered into a full M4 analysis (the ~10-min, 58×run_stats
    churn that blew the wall-clock). Reuses chapter_to_module so this map can
    never drift from app.partner_run.required_modules_for."""
    scope = _current_scope()
    if not scope:
        return None
    try:
        from agent.tools.state_tools import chapter_to_module  # noqa: PLC0415
        return frozenset(chapter_to_module(c) for c in scope)
    except Exception:
        return None


def scoped_chapters(all_chapters: list[str]) -> list[str]:
    """Filter `all_chapters` (canonical order) down to the ordered subset when a
    partner scope is set; otherwise return them unchanged."""
    scope = _current_scope()
    if not scope:
        return list(all_chapters)
    wanted = set(scope)
    subset = [c for c in all_chapters if c in wanted]
    return subset or list(all_chapters)

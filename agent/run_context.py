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


def set_report_chapters(chapters) -> None:
    """Set the ordered-chapters hint for the current run (no-op on empty)."""
    if chapters:
        report_chapters.set(tuple(chapters))
        os.environ[_ENV_KEY] = ",".join(str(c) for c in chapters)


def _current_scope() -> tuple[str, ...] | None:
    scope = report_chapters.get()
    if scope:
        return scope
    raw = os.environ.get(_ENV_KEY)
    if raw:
        return tuple(c for c in raw.split(",") if c)
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

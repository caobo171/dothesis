"""Run-scoped hints for a single headless run.

`report_chapters` is a ContextVar (not a global → isolated per run, thread-safe)
holding the chapters a PARTNER actually ordered. The headless entrypoint sets it
from the resolved order; the M5 agent reads it to compose ONLY those chapters
instead of the whole 6-chapter thesis. Unset (the interactive/chat default, or
if it doesn't propagate) → compose everything, so reading it is always safe.
"""
from __future__ import annotations

import contextvars

report_chapters: contextvars.ContextVar[tuple[str, ...] | None] = contextvars.ContextVar(
    "report_chapters", default=None
)


def set_report_chapters(chapters) -> None:
    """Set the ordered-chapters hint for the current run (no-op on empty)."""
    if chapters:
        report_chapters.set(tuple(chapters))


def scoped_chapters(all_chapters: list[str]) -> list[str]:
    """Filter `all_chapters` (canonical order) down to the ordered subset when a
    partner scope is set; otherwise return them unchanged."""
    scope = report_chapters.get()
    if not scope:
        return list(all_chapters)
    wanted = set(scope)
    subset = [c for c in all_chapters if c in wanted]
    return subset or list(all_chapters)

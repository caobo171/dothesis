"""Analytics hook for the agent layer — a no-op until the app wires it to PostHog.

Why an indirection: agent/ (and quality/) sit BELOW app/ and must never import
app/*, but the real emitter (app.analytics.emit -> PostHog) lives in app. So agent
tools and the quality rubric call `agent.analytics.emit`, which defaults to a
no-op; app.create_app() rebinds it to app.analytics.emit at startup. Same pattern
as agent/memory_hook.py. Inert by default means every emit site is safe to land
before PostHog is provisioned, and unit tests stub this `emit` directly.
"""
from __future__ import annotations

from typing import Callable


def _noop(event: str, distinct_id: str | None, properties: dict | None = None) -> None:
    return


# App overrides this at startup (agent.analytics.emit = app.analytics.emit). The
# wired impl is itself best-effort (swallows all errors), so callers need no
# try/except around it.
emit: Callable[..., None] = _noop

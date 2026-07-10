"""Cross-project advisor-theme distillation hook (F4).

A no-op until the app wires it — the agent layer must never import app/, but
distilling recurring advisor themes into per-USER memory needs the DB + user id,
which only the app has. So `mark_feedback_addressed` (an agent tool) calls this
hook when every directive is addressed, and app.create_app() sets the real impl
(resolving user_id from the store's project_id). Same indirection pattern as
agent/analytics.py.
"""
from __future__ import annotations

from typing import Any, Callable


def _noop(store: Any, advisor_feedback: list[dict]) -> None:
    return


# App overrides this at startup. Best-effort: any failure inside the wired impl
# is swallowed by the caller so it never breaks a turn.
distill_advisor_themes: Callable[..., None] = _noop

"""Best-effort agent-quality event capture to PostHog. Fire-and-forget: no-ops when
unconfigured, swallows every error, never blocks or breaks a turn. Backend-only
(agent-quality signal), not product analytics.

Landed inert (Task 1 of F5): with no POSTHOG_API_KEY set, `emit` is a no-op, so
the later features (F2/F3/F4) can be instrumented at their write sites and ship
already wired, without waiting on a provisioned PostHog project.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Cache the client (and the fact that we tried) so we build it at most once. A
# dict rather than module globals so tests can monkeypatch `_client` wholesale.
_CACHED = {"client": None, "init": False}


def _client():
    """Lazily build a PostHog client from settings, or None if unconfigured."""
    if _CACHED["init"]:
        return _CACHED["client"]
    _CACHED["init"] = True
    try:
        from .settings import get_settings  # noqa: PLC0415 — lazy: avoid import cycle + let it be inert
        s = get_settings()
        if not getattr(s, "posthog_api_key", ""):
            _CACHED["client"] = None
        else:
            from posthog import Posthog  # noqa: PLC0415 — only import the SDK when actually configured
            _CACHED["client"] = Posthog(project_api_key=s.posthog_api_key, host=s.posthog_host)
    except Exception:
        logger.debug("analytics: client init failed; disabling", exc_info=True)
        _CACHED["client"] = None
    return _CACHED["client"]


def emit(event: str, distinct_id: str | None, properties: dict | None = None) -> None:
    """Capture one agent-quality event. Best-effort — any failure is logged at debug."""
    try:
        client = _client()
        if client is None:
            return
        client.capture(distinct_id=distinct_id or "anonymous", event=event,
                       properties=properties or {})
    except Exception:
        # Analytics must never break a turn (project invariant): swallow and move on.
        logger.debug("analytics: emit(%s) failed", event, exc_info=True)

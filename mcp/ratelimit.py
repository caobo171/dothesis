"""Per-user rate limit for MCP tool calls.

Why this had to land alongside the wider tool surface: an MCP access token
carries full account authority for its hour, and a connector can call as fast as
its host will let it. With one cheap tool that was a cost question; with
generation tools in the set it becomes a "a loop in someone's client drains a
student's credits in a minute" question.

The counter is `mcp_tool_calls` — the audit table, which already records one row
per invocation with a `(user_id, created_at)` index. No second store, no Redis,
and the limit is enforced against exactly the history an admin sees on
/admin/connectors, so "why was I throttled?" is answerable from the same page.

Two tiers, because the tools differ by two orders of magnitude in cost:
reads (list_projects, check_credits) are nearly free; humanize is a 20-30s model
call; starting a thesis spends real credits. The heavy tier is deliberately
tight — DoThesis's own quota check (`check_can_start_job`) already guards thesis
runs, so this is a second gate, not the only one.

FAILS OPEN. If the counter query itself fails, the call proceeds. A database
hiccup must not look to a student like "you have been blocked" — the audit log
still records what happened either way.
"""
from __future__ import annotations

import logging

import psycopg

from oauth import _dsn

log = logging.getLogger(__name__)

# (max calls, window minutes) per tier.
LIMITS = {
    # Reads: generous. Chat clients poll and retry, and these cost ~nothing.
    "light": (120, 10),
    # One model round-trip each. 20/10min is far above real drafting use
    # (a section every 30s) and far below a runaway loop.
    "model": (20, 10),
    # Spends credits and starts a long job. The app's own quota check is the
    # primary gate; this stops a client retrying a failed start in a tight loop.
    "heavy": (5, 60),
}


class RateLimited(Exception):
    def __init__(self, tier: str, limit: int, minutes: int):
        self.tier, self.limit, self.minutes = tier, limit, minutes
        super().__init__(
            f"Rate limit reached: at most {limit} {tier}-tier calls per "
            f"{minutes} minutes. Wait a moment and try again.")


def check(user_id: str | None, tools_in_tier: list[str], tier: str) -> None:
    """Raise RateLimited if `user_id` is over the tier's budget.

    Counts calls to the tools IN THIS TIER only, so a burst of cheap reads can
    never lock someone out of the humanize they actually came for.
    """
    if not user_id or tier not in LIMITS:
        return
    limit, minutes = LIMITS[tier]
    try:
        with psycopg.connect(_dsn(), connect_timeout=5) as conn:
            n = conn.execute(
                "SELECT count(*) FROM mcp_tool_calls "
                "WHERE user_id = %s::uuid AND tool = ANY(%s) "
                "AND created_at > now() - make_interval(mins => %s)",
                (user_id, tools_in_tier, minutes)).fetchone()[0]
    except Exception:  # noqa: BLE001 — see "FAILS OPEN" above
        log.exception("rate-limit check failed; allowing the call")
        return
    if n >= limit:
        raise RateLimited(tier, limit, minutes)

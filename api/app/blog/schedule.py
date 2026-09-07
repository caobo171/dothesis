"""When each row of a batch goes live.

WELE's formula, unchanged:

    go_live = start + week * 7d + floor(slot * 7d / per_week)

where `week = index // per_week` and `slot = index % per_week`. It spreads a
batch evenly across the days of each week instead of dumping it all at
midnight, which is what a thousand pages appearing in one crawl looks like to
Google.

A date already in the past inserts as published; a future one inserts as
scheduled and `visible_filter()` reveals it when the date arrives. There is no
job to run in between.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import STATUS_PUBLISHED, STATUS_SCHEDULED

# The readers are in Vietnam, so a bare `--schedule-start 2026-09-10` means
# midnight in Hanoi. Reading it as UTC would put every tranche at 7am local.
VN_TZ = timezone(timedelta(hours=7))

WEEK = timedelta(days=7)


def parse_start_date(text: str) -> datetime:
    """`YYYY-MM-DD` at midnight Vietnam time. Raises ValueError otherwise."""
    parsed = datetime.strptime(text, "%Y-%m-%d")
    return parsed.replace(tzinfo=VN_TZ)


def go_live_at(index: int, start: datetime, per_week: int) -> datetime:
    if per_week < 1:
        raise ValueError("per_week must be at least 1")
    week, slot = divmod(index, per_week)
    within_week = (slot * int(WEEK.total_seconds())) // per_week
    return start + week * WEEK + timedelta(seconds=within_week)


def plan_status(
    go_live: datetime,
    now: datetime | None = None,
) -> tuple[int, datetime, datetime | None]:
    """(status, published_at, scheduled_at) for a row going live at `go_live`."""
    moment = now or datetime.now(timezone.utc)
    if go_live <= moment:
        return STATUS_PUBLISHED, go_live, None
    return STATUS_SCHEDULED, go_live, go_live

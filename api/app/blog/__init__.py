"""Blog service package.

The one rule everything else hangs off is `visible_filter()`: what the public
is allowed to see. It lives here, at the top of the package, because the same
rule has to hold for the listing, the detail route, the category counts, the
sitemap, the SEO audit and the link audit — six places that would otherwise
each get to remember half of it.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Status values, mirroring WELE's BlogPostModel.STATUS. Small integers rather
# than an enum type so a status can be added without a migration.
STATUS_DRAFT = 0
STATUS_PUBLISHED = 1
STATUS_SCHEDULED = 2

# Every status a post can hold and still be destined for the public. Not the
# same thing as "visible": a scheduled post is invisible until its date
# arrives, but it already owns its keyword, so the duplicate guard counts it.
LIVE_OR_PENDING = (STATUS_PUBLISHED, STATUS_SCHEDULED)


def visible_filter(now: datetime | None = None):
    """The SQLAlchemy condition for "the public may see this post".

    Published, or scheduled with a date that has passed. There is no cron job
    flipping status 2 to status 1 — the read side does the arithmetic, so a
    scheduled post goes live on time even if nothing is running.

    `now` is injectable so tests can put the clock either side of a scheduled
    date without sleeping.
    """
    from sqlalchemy import and_, or_  # noqa: PLC0415 — keep import cost off the CLI

    from ..models import BlogPost  # noqa: PLC0415 — avoids a package-import cycle

    moment = now or datetime.now(timezone.utc)
    return or_(
        BlogPost.status == STATUS_PUBLISHED,
        and_(
            BlogPost.status == STATUS_SCHEDULED,
            BlogPost.scheduled_at.isnot(None),
            BlogPost.scheduled_at <= moment,
        ),
    )


def is_visible(post, now: datetime | None = None) -> bool:
    """The same rule in Python, for rows already in memory."""
    moment = now or datetime.now(timezone.utc)
    if post.status == STATUS_PUBLISHED:
        return True
    if post.status == STATUS_SCHEDULED and post.scheduled_at is not None:
        scheduled = post.scheduled_at
        if scheduled.tzinfo is None:  # a naive column value is UTC by convention
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        return scheduled <= moment
    return False

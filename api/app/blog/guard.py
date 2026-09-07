"""Refuse to publish a post that competes with one already in the bank.

Port of WELE's `services/blog/duplicate.guard.ts`. A warning was considered
there and rejected: warnings get clicked past, and the cost is not a bad save,
it is two pages splitting one ranking for months before anyone notices. At a
thousand posts that argument only gets stronger.

The override is deliberately expensive. It requires prose, it is stored on the
row, and `index.py` prints it into `docs/blog-index.md` where it gets read
later. A text box whose contents end up committed to git is not something
anyone fills in reflexively.

WELE's calibration finding, kept: the block keys on `focus_keyword` ONLY, with
no title fallback, unlike `find_clashes`' general-purpose default. Running the
audit against WELE's live corpus with a `focus || title` key reported 24
clashes, most of them template-title families (two different teachers sharing
one landing-page title template scored 75%, higher than some genuine
duplicates at 64%), so no threshold separates them. A post with no
`focus_keyword` is therefore never a subject and never a candidate.

DEVIATION from the design's §9 wording, stated here because it matters:
candidates are posts with status published OR scheduled, not posts that pass
`visible_filter()`. A `create` run inserts a thousand posts almost all
future-scheduled; if candidacy required present visibility, the guard would be
blind to everything the same run just inserted and the CLI's per-seed check
would be theatre. A scheduled post already owns its keyword and publishes
itself on a timer, so it counts. This matches WELE's own query.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import LIVE_OR_PENDING
from .similarity import Candidate, Clash, find_clashes

# Shortest override that could plausibly be a reason rather than a keystroke.
MIN_OVERRIDE_LENGTH = 25


@dataclass
class GuardResult:
    blocked: bool
    message: str | None = None
    clashes: list[Clash] = field(default_factory=list)


def build_refusal(clashes: Iterable[Clash]) -> str:
    lines = [
        f'"{c.slug}" ({c.score * 100:.0f}% overlap on the same target keyword '
        f'"{c.focus}", both "{c.intent}")'
        for c in clashes
    ]
    return (
        "This post targets the same keyword as something already in the bank: "
        + "; ".join(lines) + ". "
        "Two pages chasing one target keyword split their own ranking. Re-angle "
        "this post onto a different keyword, or improve the existing one instead. "
        "If it genuinely belongs as a separate page, send duplicate_override_reason "
        "explaining why — it is stored on the post and published in "
        "docs/blog-index.md."
    )


def build_candidates(posts: Iterable[Any]) -> list[Candidate]:
    """The `Candidate` list `find_clashes` compares against.

    Every survivor is fingerprinted by its keyword alone; `title` is always the
    empty string so `find_clashes`' internal focus-or-title fallback can never
    reach a title.
    """
    out: list[Candidate] = []
    for p in posts:
        keyword = (getattr(p, "focus_keyword", None) or "").strip()
        if not keyword:
            continue
        out.append(Candidate(id=getattr(p, "id", None), slug=p.slug,
                             locale=p.locale, title="", focus=keyword))
    return out


def assert_no_duplicate(
    db: Session,
    seed: Mapping[str, Any],
    exclude_id: Any = None,
) -> GuardResult:
    """Does `seed` collide with a post already published or scheduled?

    `seed` is the seed-shaped body (or a dict with `locale`, `focus_keyword`
    and optionally `duplicate_override_reason`). `exclude_id` is the row being
    updated, so a post never blocks itself.
    """
    keyword = (seed.get("focus_keyword") or "").strip()
    # No target keyword means nothing to key the block on. This is "never
    # block", not "fall back to the title" — see the module header.
    if not keyword:
        return GuardResult(blocked=False)

    locale = seed.get("locale") or "vi"
    subject = Candidate(id=exclude_id, slug="", locale=locale, title="", focus=keyword)

    from ..models import BlogPost  # noqa: PLC0415 — avoids a package-import cycle

    rows = db.scalars(
        select(BlogPost).where(
            BlogPost.locale == locale,
            BlogPost.status.in_(LIVE_OR_PENDING),
        )
    ).all()

    clashes = find_clashes(subject, build_candidates(rows))
    if not clashes:
        return GuardResult(blocked=False)

    override = (seed.get("duplicate_override_reason") or "").strip()
    if len(override) >= MIN_OVERRIDE_LENGTH:
        # Not blocked, but the clashes still come back: the caller records them
        # and the index file prints the reason next to them.
        return GuardResult(blocked=False, clashes=clashes)

    return GuardResult(blocked=True, message=build_refusal(clashes), clashes=clashes)

"""Read-only audits over the live bank. Nothing here writes.

`audit_seo` answers "what has this blog already covered, and where do two
pages chase one ranking". Content planned from keyword research alone, with no
record of what is already published, is how WELE ended up with two posts in
the same SERP competing with each other.

`audit_links` answers "does every internal link land somewhere". WELE's crawl
turned up 404s at paths like `/blog/vi/1-the-interview`: an author wrote a
href with no leading slash, the browser resolved it against the post's own
directory, and invented a URL that never existed. In markdown the same mistake
is `[text](cronbach-alpha-la-gi)`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import visible_filter
from .markdown import links, word_count
from .similarity import CLASH_THRESHOLD, classify, overlap, tokens

# Non-blog destinations a post is allowed to link to. Anything else that starts
# with a slash and is not a known post or category is a broken link.
ALLOWED_ROUTES: frozenset[str] = frozenset({
    "/", "/landing", "/signup", "/login", "/chat",
})

# Default word floor for the thin-content report. Higher than WELE's 1,200
# because this engine targets 1,800 to 2,400 words per post, so anything under
# 1,500 came out of a failed generation rather than a short-by-design page.
DEFAULT_THIN = 1500


@dataclass
class PostRow:
    slug: str
    locale: str
    title: str
    focus: str
    words: int
    has_meta_description: bool
    intent_class: str
    intent_tokens: set = field(default_factory=set, repr=False)


@dataclass
class ClashPair:
    a: PostRow
    b: PostRow
    score: float
    intent: str


@dataclass
class SeoReport:
    rows: list[PostRow]
    clashes: list[ClashPair]
    thin: list[PostRow]
    no_meta: list[PostRow]
    no_focus: list[PostRow]
    thin_floor: int


def audit_seo(db: Session, locale: str | None = None,
              thin_floor: int = DEFAULT_THIN) -> SeoReport:
    from ..models import BlogPost  # noqa: PLC0415

    conditions = [visible_filter()]
    if locale:
        conditions.append(BlogPost.locale == locale)
    posts = db.scalars(
        select(BlogPost).where(*conditions).order_by(desc(BlogPost.published_at))).all()

    rows = []
    for p in posts:
        # The fingerprint: focus keyword if set, else the title, since a post
        # with no focus keyword still occupies a topic and still competes. The
        # save-time guard is stricter — see guard.py.
        fingerprint = p.focus_keyword or p.title or ""
        rows.append(PostRow(
            slug=p.slug, locale=p.locale, title=p.title or "",
            focus=p.focus_keyword or "", words=word_count(p.body),
            has_meta_description=bool(p.meta_description),
            intent_class=classify(fingerprint), intent_tokens=tokens(fingerprint),
        ))

    clashes: list[ClashPair] = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a.locale != b.locale or a.intent_class != b.intent_class:
                continue  # same words AND same intent; either alone is not competition
            score = overlap(a.intent_tokens, b.intent_tokens)
            if score >= CLASH_THRESHOLD:
                clashes.append(ClashPair(a=a, b=b, score=score, intent=a.intent_class))

    return SeoReport(
        rows=rows,
        clashes=sorted(clashes, key=lambda c: c.score, reverse=True),
        thin=[r for r in rows if r.words < thin_floor],
        no_meta=[r for r in rows if not r.has_meta_description],
        no_focus=[r for r in rows if not r.focus],
        thin_floor=thin_floor,
    )


@dataclass
class LinkFinding:
    href: str
    reason: str
    posts: list[str] = field(default_factory=list)


@dataclass
class LinkReport:
    checked: int
    total_links: int
    findings: list[LinkFinding]


def audit_links(db: Session, extra_allowed: set[str] | None = None) -> LinkReport:
    from ..models import BlogPost  # noqa: PLC0415

    posts = db.scalars(select(BlogPost).where(visible_filter())).all()

    known: set[str] = set(ALLOWED_ROUTES) | set(extra_allowed or ())
    locales = {p.locale for p in posts}
    # A link to a post that is scheduled but not yet live is not broken: the
    # linking post is on the same schedule, and a scheduled bank would otherwise
    # report every forward link as a 404 until the last tranche lands.
    from . import LIVE_OR_PENDING  # noqa: PLC0415
    for locale, slug in db.execute(
            select(BlogPost.locale, BlogPost.slug)
            .where(BlogPost.status.in_(LIVE_OR_PENDING))).all():
        known.add(f"/blog/{locale}/{slug}")
    for locale in locales:
        known.add(f"/blog/{locale}")
    from ..models import BlogCategory  # noqa: PLC0415
    # A category hub exists at its OWN locale only. Crossing every category with
    # every locale, which is what this did while categories were locale-less,
    # would now green-light a Vietnamese post linking to an English-only hub.
    # `chu-de` stays the segment in both languages: the web route is a static
    # /blog/[locale]/chu-de/[category], so the two editions share the path.
    for category in db.scalars(select(BlogCategory)).all():
        known.add(f"/blog/{category.locale}/chu-de/{category.slug}")

    findings: dict[str, LinkFinding] = {}
    total = 0
    for p in posts:
        where = f"{p.slug} [{p.locale}]"
        for _, href in links(p.body or ""):
            total += 1
            if not href or href.startswith("#"):
                continue
            if href.startswith(("http://", "https://", "mailto:", "tel:", "{{")):
                continue
            if not href.startswith("/"):
                # Schemeless and not root-relative: the browser resolves this
                # against /blog/{locale}/ and 404s.
                reason = "relative href, resolves under the post's own directory"
            else:
                target = href.split("#", 1)[0].split("?", 1)[0].rstrip("/") or "/"
                if target in known:
                    continue
                reason = "no visible post, category or allow-listed route"
            finding = findings.setdefault(href, LinkFinding(href=href, reason=reason))
            finding.posts.append(where)

    return LinkReport(checked=len(posts), total_links=total,
                      findings=sorted(findings.values(), key=lambda f: -len(f.posts)))

"""Seed JSON in, blog rows out.

The seed schema is §12 of the design. One JSON file per post, `NNNN-{slug}`,
under `api/data/blog-seeds/{locale}/posts/`, with `categories.json` beside the
`posts/` directory. That layout is WELE's `--dir` layout: the numeric prefix is
the publish order, so a `create` run reproduces the planned tranches exactly.

Validation is strict and refuses rather than repairs. A seed with a slug of
`Cronbach Alpha Là Gì` is not quietly normalised, because the slug is already
in the backlog, in the sibling lists of neighbouring posts, and in whatever
internal links the writer emitted; silently changing it here would break those
links and nobody would find out until a crawl.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from .markdown import reading_time
from .schedule import plan_status

SEED_SCHEMA = "dothesis-blog-seed/1"

# The locale the bank launched with, and the fallback for anything that predates
# categories being per-locale. Never used to bind a post: a seed always carries
# its own `locale`, and that is what picks the category row.
DEFAULT_LOCALE = "vi"
MAX_LOCALE_LENGTH = 8  # blog_categories.locale / blog_posts.locale are String(8)

# The nine categories of §6. A category exists only once its own name has
# measured search volume, which is why this is a closed list and a seed
# pointing outside it is an error rather than a new category.
CATEGORY_SLUGS: tuple[str, ...] = (
    "spss",
    "thong-ke",
    "khao-sat",
    "nghien-cuu-khoa-hoc",
    "khoa-luan-tot-nghiep",
    "smartpls",
    "phan-tich-du-lieu",
    "luan-van-thac-si",
    "mo-hinh-nghien-cuu",
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "schema", "title", "slug", "locale", "meta_title", "meta_description",
    "focus_keyword", "excerpt", "category", "archetype", "body",
)

LIST_FIELDS: tuple[str, ...] = ("secondary_keywords", "tags", "sibling_slugs", "images")

# How the page's demand was established (design §5). `measured` means the focus
# keyword returned its own search volume; `unmeasured` means the measurement
# source had nothing to say about it. Since 2026-09-08 both publish: volume sets
# priority order, and the QA gate holds an unmeasured page to twice the
# distinctness bar because quality is then the only thing keeping the bank clear
# of Google's scaled-content-abuse policy.
GATE_STATUSES: tuple[str, ...] = ("measured", "unmeasured")
DEFAULT_GATE_STATUS = "measured"

# `family-inferred` was what an unmeasured page was called until 2026-09-08, when
# the gate stopped inferring demand from a keyword's family. 149 seed files on
# disk carry it, and rewriting them all to change a word would touch every seed
# in the bank for no gain, so the old spelling stays readable and normalises on
# load. Nothing writes it any more.
DEPRECATED_GATE_STATUSES: dict[str, str] = {"family-inferred": "unmeasured"}

MAX_SLUG_LENGTH = 120

_COMBINING = dict.fromkeys(range(0x0300, 0x0370))


class SeedError(ValueError):
    """A seed that cannot become a post. Carries the field and the file."""

    def __init__(self, message: str, *, field: str | None = None,
                 source: str | Path | None = None):
        self.field = field
        self.source = str(source) if source else None
        prefix = f"{self.source}: " if self.source else ""
        super().__init__(f"{prefix}{message}")


def normalize_slug(text: str) -> str:
    """ASCII, lowercase, hyphenated, at most 120 characters.

    The same transformation as `markdown.slugify` (see its docstring for the
    steps), plus the length cap. Kept as its own function because a post slug
    is a URL that has to survive a database column, while a heading id only has
    to survive the page.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = decomposed.translate(_COMBINING).replace("đ", "d").replace("Đ", "d")
    slug = re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH].strip("-")


def validate_seed(data: Any, *, source: str | Path | None = None) -> dict:
    """Return a normalised copy of `data`, or raise `SeedError`."""
    if not isinstance(data, Mapping):
        raise SeedError("seed must be a JSON object", source=source)

    seed = dict(data)

    for field in REQUIRED_FIELDS:
        if field not in seed:
            raise SeedError(f"missing required field: {field}", field=field, source=source)
        value = seed[field]
        if not isinstance(value, str) or not value.strip():
            raise SeedError(f"field must be a non-empty string: {field}",
                            field=field, source=source)

    if seed["schema"] != SEED_SCHEMA:
        raise SeedError(f"schema is {seed['schema']!r}, expected {SEED_SCHEMA!r}",
                        field="schema", source=source)

    if seed["category"] not in CATEGORY_SLUGS:
        raise SeedError(
            f"unknown category {seed['category']!r}; expected one of "
            + ", ".join(CATEGORY_SLUGS),
            field="category", source=source)

    slug = seed["slug"]
    if len(slug) > MAX_SLUG_LENGTH:
        raise SeedError(f"slug is {len(slug)} characters, the limit is {MAX_SLUG_LENGTH}",
                        field="slug", source=source)
    if slug != normalize_slug(slug):
        raise SeedError(f"slug is not normalized; use {normalize_slug(slug)!r}",
                        field="slug", source=source)

    for field in LIST_FIELDS:
        value = seed.get(field) or []
        if not isinstance(value, list):
            raise SeedError(f"field must be a list: {field}", field=field, source=source)
        seed[field] = value

    volume = seed.get("focus_keyword_volume")
    if volume is not None and not isinstance(volume, int):
        raise SeedError("focus_keyword_volume must be an integer",
                        field="focus_keyword_volume", source=source)

    # Optional, but defaulted here rather than at every read site: this value
    # decides whether the post publishes at all, and a `.get("gate_status")`
    # spelled out in three callers is three chances to drift from the list.
    gate_status = seed.get("gate_status") or DEFAULT_GATE_STATUS
    gate_status = DEPRECATED_GATE_STATUSES.get(gate_status, gate_status)
    if gate_status not in GATE_STATUSES:
        raise SeedError(
            f"gate_status is {gate_status!r}, expected one of "
            + ", ".join(GATE_STATUSES),
            field="gate_status", source=source)
    seed["gate_status"] = gate_status

    return seed


def is_unmeasured(seed: Mapping[str, Any]) -> bool:
    """True when the measurement source returned no volume for the focus keyword.

    Reporting only, since 2026-09-08. It used to force the post to DRAFT; now it
    tells the operator how much of a tranche is publishing on the quality gates'
    word rather than on a number.
    """
    status = seed.get("gate_status") or DEFAULT_GATE_STATUS
    return DEPRECATED_GATE_STATUSES.get(status, status) == "unmeasured"


def load_seed(path: str | Path) -> dict:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SeedError(f"invalid JSON ({e.msg} at line {e.lineno})", source=path) from e
    except OSError as e:
        raise SeedError(f"cannot read seed ({e.strerror})", source=path) from e
    return validate_seed(raw, source=path)


def _post_files(directory: Path) -> list[Path]:
    """`posts/*.json` when that layout is present, else the directory itself.

    The canonical layout has a `posts/` subdirectory beside `categories.json`.
    The flat fallback exists so `--dir` also works on an ad-hoc folder of seed
    files, which is what anyone repairing a handful of posts actually has.
    """
    posts_dir = directory / "posts"
    if posts_dir.is_dir():
        return sorted(posts_dir.glob("*.json"))
    return sorted(p for p in directory.glob("*.json") if p.name != "categories.json")


def load_dir(directory: str | Path) -> list[tuple[Path, dict]]:
    """(path, seed) for every post file, sorted by filename.

    Sorted because the `NNNN-` prefix IS the publish order: the schedule walks
    this list and assigns go-live dates by index.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise SeedError("seed directory not found", source=directory)
    return [(p, load_seed(p)) for p in _post_files(directory)]


def seeds_locale(seeds: list[tuple[Path, dict]]) -> str | None:
    """The one locale a batch of seeds agrees on, or None if it does not.

    The seeds are the honest source for "what language is this directory".
    The directory NAME is not: `--dir` also accepts a flat folder of repair
    files (see `_post_files`) and `docs/seo/fixtures/seeds`, neither of which
    is named after a locale. Nor is the loader's own default, which would
    silently hand an English batch the Vietnamese categories.

    None means the caller has to be told rather than guessed at.
    """
    locales = {seed["locale"] for _, seed in seeds}
    return locales.pop() if len(locales) == 1 else None


def load_categories(directory: str | Path, *,
                    default_locale: str | None = DEFAULT_LOCALE) -> list[dict]:
    """`categories.json` beside `posts/`, or an empty list if absent.

    Every returned row carries a resolved `locale`, because a category row is
    now one language edition of a hub and the wrong one renders Vietnamese
    headings on an English page. A row may name its own `locale` (which is what
    `docs/seo/categories.en.json` does, so the file is self-describing wherever
    it is copied); otherwise it takes `default_locale`, which the CLI fills in
    from the locale the seeds in the same run agree on.

    `default_locale=None` means nothing could be inferred — a mixed or empty
    batch — and then the file has to say so itself rather than be guessed at.
    """
    path = Path(directory) / "categories.json"
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SeedError(f"invalid JSON ({e.msg} at line {e.lineno})", source=path) from e
    if not isinstance(rows, list):
        raise SeedError("categories.json must be a JSON array", source=path)

    out: list[dict] = []
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("slug"):
            raise SeedError("every category needs a slug", source=path)
        if row["slug"] not in CATEGORY_SLUGS:
            raise SeedError(f"unknown category {row['slug']!r}", source=path)
        locale = row.get("locale") or default_locale
        if not locale or not isinstance(locale, str):
            raise SeedError(
                f"cannot tell which locale category {row['slug']!r} belongs to; "
                'add "locale" to categories.json (the seeds beside it do not agree '
                "on one)", field="locale", source=path)
        if len(locale) > MAX_LOCALE_LENGTH:
            raise SeedError(f"locale {locale!r} is longer than {MAX_LOCALE_LENGTH} characters",
                            field="locale", source=path)
        out.append({**row, "locale": locale})
    return out


def category_index(db: Session) -> dict[tuple[str, str], Any]:
    """`{(locale, slug): id}` for every category row.

    The key is a pair and not a slug on purpose: `spss` exists once per locale
    now, so a mapping keyed on the slug alone cannot express the right answer
    and would quietly bind an English post to the Vietnamese hub.
    """
    from ..models import BlogCategory  # noqa: PLC0415

    return {(c.locale, c.slug): c.id for c in db.scalars(select(BlogCategory)).all()}


def upsert_categories(db: Session, categories: list[dict]) -> dict[tuple[str, str], Any]:
    """Create or refresh the category rows; return `{(locale, slug): id}`.

    Refresh rather than skip, unlike WELE's create.blog: the intro copy is the
    only content a category page has of its own, and it gets rewritten far more
    often than the category list changes.

    Scoped by locale on both halves of that: the lookup that decides create-vs-
    refresh matches `(locale, slug)`, so loading `data/blog-seeds/en` adds seven
    English rows beside the Vietnamese seven instead of overwriting their copy.
    """
    from ..models import BlogCategory  # noqa: PLC0415

    ids: dict[tuple[str, str], Any] = {}
    for order, row in enumerate(categories):
        slug = row["slug"]
        # `load_categories` always resolves this; the fallback is for a
        # hand-built dict, and it points at the locale the bank launched with
        # rather than at whatever happens to be first in the table.
        locale = row.get("locale") or DEFAULT_LOCALE
        name = row.get("name") or row.get("display_name") or slug
        existing = db.scalar(select(BlogCategory).where(
            BlogCategory.locale == locale, BlogCategory.slug == slug))
        if existing is None:
            existing = BlogCategory(locale=locale, slug=slug)
            db.add(existing)
        existing.name = name
        existing.display_name = row.get("display_name") or name
        existing.intro_md = row.get("intro_md")
        existing.sort_order = int(row.get("sort_order", order))
        db.flush()
        ids[(locale, slug)] = existing.id
    db.commit()
    return ids


def _apply_content(post, seed: Mapping[str, Any], category_ids: Mapping[tuple[str, str], Any]) -> None:
    """Everything a seed owns. Status and dates are deliberately NOT here."""
    post.title = seed["title"]
    post.body = seed["body"].strip()
    post.excerpt = seed.get("excerpt")
    post.meta_title = seed.get("meta_title")
    post.meta_description = seed.get("meta_description")
    post.focus_keyword = seed.get("focus_keyword")
    post.secondary_keywords = list(seed.get("secondary_keywords") or [])
    post.focus_keyword_volume = seed.get("focus_keyword_volume")
    post.tags = list(seed.get("tags") or [])
    post.archetype = seed.get("archetype")
    post.source_batch = seed.get("source_batch")
    # A translated seed names the post it came from; an original names itself,
    # so both editions of one article carry the same key and can point at each
    # other. Falling back to the slug means a bank written in one language needs
    # no new field to become translatable later.
    post.translation_key = seed.get("translation_key") or seed.get("slug")
    post.canonical_url = seed.get("canonical_url")
    # Keyed by (locale, slug) — see `category_index`. A seed whose locale has no
    # such category binds to nothing rather than to another language's hub;
    # category_id is nullable and a wrong category is worse than none.
    post.category_id = category_ids.get((seed["locale"], seed.get("category")))
    # `images` stays in the schema for the day there is public image hosting;
    # until then a seed may carry an explicit image_url and nothing else.
    post.image_url = seed.get("image_url")
    # Recomputed rather than trusted: a seed's own reading_time drifts the
    # moment anyone edits the body.
    post.reading_time = seed.get("reading_time") or reading_time(seed["body"])
    if seed.get("duplicate_override_reason"):
        post.duplicate_override_reason = seed["duplicate_override_reason"]


def find_post(db: Session, locale: str, slug: str):
    from ..models import BlogPost  # noqa: PLC0415

    return db.scalar(select(BlogPost).where(BlogPost.locale == locale, BlogPost.slug == slug))


def create_from_seed(
    db: Session,
    seed: Mapping[str, Any],
    category_ids: Mapping[tuple[str, str], Any],
    *,
    go_live: datetime | None = None,
    now: datetime | None = None,
) -> tuple[str, Any]:
    """Insert the post, or report that `(locale, slug)` already exists.

    Skip rather than update, exactly as WELE's create.blog does: `create` is
    re-run to fill in what a previous run did not finish, and it must never
    overwrite a post someone has since edited by hand. `update-from-seed` is
    the command for that.
    """
    from ..models import BlogPost  # noqa: PLC0415

    moment = now or datetime.now(timezone.utc)
    existing = find_post(db, seed["locale"], seed["slug"])
    if existing is not None:
        return "skipped", existing

    # Every seed publishes on its schedule, unmeasured ones included (rule
    # changed 2026-09-08). An unmeasured page used to be forced to DRAFT here on
    # the theory that unproven demand must not go live; the three quality gates
    # decide that now, and a page that cleared them is worth publishing whether
    # or not Google Ads has a number for its keyword.
    status, published_at, scheduled_at = plan_status(go_live or moment, now=moment)
    post = BlogPost(locale=seed["locale"], slug=seed["slug"], status=status,
                    published_at=published_at, scheduled_at=scheduled_at,
                    created_at=moment, updated_at=moment)
    _apply_content(post, seed, category_ids)
    db.add(post)
    db.commit()
    return "created", post


def upsert_from_seed(
    db: Session,
    seed: Mapping[str, Any],
    category_ids: Mapping[tuple[str, str], Any],
    *,
    go_live: datetime | None = None,
    now: datetime | None = None,
    status: int | None = None,
    published_at: datetime | None = None,
    scheduled_at: datetime | None = None,
) -> tuple[str, Any]:
    """Create the post, or refresh an existing one from the seed.

    An existing post keeps its schedule unless the caller passes an explicit
    one. Re-running the writer over a live bank must not drag a scheduled post
    forward or push a published one back.
    """
    from ..models import BlogPost  # noqa: PLC0415

    moment = now or datetime.now(timezone.utc)
    existing = find_post(db, seed["locale"], seed["slug"])

    if existing is None:
        planned_status, planned_published, planned_scheduled = plan_status(
            go_live or moment, now=moment)
        # No draft branch here either, for the same reason as `create_from_seed`:
        # the two inserts have to agree, or the same seed would publish through
        # one command and not the other.
        existing = BlogPost(
            locale=seed["locale"], slug=seed["slug"],
            status=status if status is not None else planned_status,
            published_at=published_at or planned_published,
            scheduled_at=scheduled_at if status is not None else planned_scheduled,
            created_at=moment, updated_at=moment,
        )
        db.add(existing)
        action = "created"
    else:
        action = "updated"
        if status is not None:
            existing.status = status
            existing.published_at = published_at or existing.published_at
            existing.scheduled_at = scheduled_at

    _apply_content(existing, seed, category_ids)
    existing.updated_at = moment
    db.commit()
    return action, existing

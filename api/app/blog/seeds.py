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

from . import STATUS_DRAFT
from .markdown import reading_time
from .schedule import plan_status

SEED_SCHEMA = "dothesis-blog-seed/1"

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
# keyword returned its own search volume. `family-inferred` means it did not and
# the gate carried it on its family's evidence instead — either the thin-keyword
# aggregate rule or the unmeasured fill. Both are real pages with unproven
# demand, which is a different thing from a page we know people search for, so
# `create` inserts them as drafts and never spends a slot on them.
GATE_STATUSES: tuple[str, ...] = ("measured", "family-inferred")
DEFAULT_GATE_STATUS = "measured"

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
    if gate_status not in GATE_STATUSES:
        raise SeedError(
            f"gate_status is {gate_status!r}, expected one of "
            + ", ".join(GATE_STATUSES),
            field="gate_status", source=source)
    seed["gate_status"] = gate_status

    return seed


def is_family_inferred(seed: Mapping[str, Any]) -> bool:
    """True when the gate carried this page on its family, not on its own volume.

    The single spelling of the draft rule. `create_from_seed` reads it to force
    status DRAFT, and `cli.cmd_create` reads it to skip the schedule slot.
    """
    return (seed.get("gate_status") or DEFAULT_GATE_STATUS) == "family-inferred"


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


def load_categories(directory: str | Path) -> list[dict]:
    """`categories.json` beside `posts/`, or an empty list if absent."""
    path = Path(directory) / "categories.json"
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SeedError(f"invalid JSON ({e.msg} at line {e.lineno})", source=path) from e
    if not isinstance(rows, list):
        raise SeedError("categories.json must be a JSON array", source=path)
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("slug"):
            raise SeedError("every category needs a slug", source=path)
        if row["slug"] not in CATEGORY_SLUGS:
            raise SeedError(f"unknown category {row['slug']!r}", source=path)
    return [dict(r) for r in rows]


def upsert_categories(db: Session, categories: list[dict]) -> dict[str, Any]:
    """Create or refresh the category rows; return `{slug: id}`.

    Refresh rather than skip, unlike WELE's create.blog: the intro copy is the
    only content a category page has of its own, and it gets rewritten far more
    often than the category list changes.
    """
    from ..models import BlogCategory  # noqa: PLC0415

    ids: dict[str, Any] = {}
    for order, row in enumerate(categories):
        slug = row["slug"]
        name = row.get("name") or row.get("display_name") or slug
        existing = db.scalar(select(BlogCategory).where(BlogCategory.slug == slug))
        if existing is None:
            existing = BlogCategory(slug=slug)
            db.add(existing)
        existing.name = name
        existing.display_name = row.get("display_name") or name
        existing.intro_md = row.get("intro_md")
        existing.sort_order = int(row.get("sort_order", order))
        db.flush()
        ids[slug] = existing.id
    db.commit()
    return ids


def _apply_content(post, seed: Mapping[str, Any], category_ids: Mapping[str, Any]) -> None:
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
    post.canonical_url = seed.get("canonical_url")
    post.category_id = category_ids.get(seed.get("category"))
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
    category_ids: Mapping[str, Any],
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

    if is_family_inferred(seed):
        # Unproven demand never publishes itself. The page is stored so it is
        # ready the day its keyword is measured, but it goes in as a DRAFT with
        # no dates: `visible_filter()` hides status 0 and `--reschedule` only
        # walks status 2, so nothing promotes it by accident. Measuring the
        # keyword and re-running `update-from-seed` is the only way out.
        status, published_at, scheduled_at = STATUS_DRAFT, None, None
    else:
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
    category_ids: Mapping[str, Any],
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
        # Same draft rule as `create_from_seed`: this branch is an insert too,
        # and `update-from-seed` over a fresh inferred seed must not publish
        # what `create` would have drafted. An explicit `status` still wins —
        # that is the admin route deliberately overriding the gate.
        if status is None and is_family_inferred(seed):
            planned_status, planned_published, planned_scheduled = STATUS_DRAFT, None, None
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

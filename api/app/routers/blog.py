"""Public blog reads.

POST-only with plain `BaseModel` bodies and no `current_user`, the shape
`routers/auth.py` uses for unauthenticated endpoints. Read-only operations go
through POST like everything else in this API (see CLAUDE.md): the web client
gets one fetch helper and one error path.

Every query here filters through `app.blog.visible_filter()`. Nothing in this
module is allowed to write its own version of "is this post public".
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..blog import visible_filter
from ..db import db_session
from ..models import BlogCategory, BlogPost

router = APIRouter(prefix="/blog", tags=["blog"])

#: Where post-body images live in the bucket. A dedicated prefix, well away
#: from `users/<uid>/projects/...`, because the read route below is public and
#: the prefix is the boundary between what may be served and what may not.
BLOG_IMAGE_PREFIX = "blog/images/"

#: The only key shape the public image route will serve: a sha256 hex digest
#: plus a known extension. The key arrives in a URL, so anything looser is a
#: way to read arbitrary objects out of a bucket that also holds every
#: student's private uploads.
_IMAGE_KEY = re.compile(r"^[a-f0-9]{64}\.(png|jpg|webp|gif)$")

_IMAGE_CONTENT_TYPE = {"png": "image/png", "jpg": "image/jpeg",
                       "webp": "image/webp", "gif": "image/gif"}

MAX_PAGE_SIZE = 50
MAX_RELATED = 5
# A sitemap over this many URLs has to be split into an index anyway, and the
# generator on the web side is not built for that yet.
SITEMAP_LIMIT = 5000
# How many recent posts the tag-based half of "related" looks through. Tag
# overlap against a variable-length list is more SQL than it is worth at this
# corpus size, so it happens in Python over a bounded window.
RELATED_SCAN = 200


class ListBody(BaseModel):
    locale: str = "vi"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=MAX_PAGE_SIZE)
    category: str | None = None
    q: str | None = None


class GetBody(BaseModel):
    locale: str = "vi"
    slug: str


class CategoriesBody(BaseModel):
    locale: str = "vi"


class SitemapBody(BaseModel):
    locale: str | None = None


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def category_dict(category: BlogCategory | None) -> dict | None:
    if category is None:
        return None
    return {
        "slug": category.slug,
        "name": category.name,
        "display_name": category.display_name,
        "intro_md": category.intro_md,
        "sort_order": category.sort_order,
    }


def compact(post: BlogPost, category: BlogCategory | None) -> dict:
    """A listing card. No body: a page of twelve posts would be ~200KB with it."""
    return {
        "id": str(post.id),
        "locale": post.locale,
        "slug": post.slug,
        "title": post.title,
        "excerpt": post.excerpt,
        "image_url": post.image_url,
        "tags": post.tags or [],
        "category": category_dict(category),
        "published_at": iso(post.published_at),
        "updated_at": iso(post.updated_at),
        "reading_time": post.reading_time,
        "views": post.views,
    }


def full(post: BlogPost, category: BlogCategory | None) -> dict:
    out = compact(post, category)
    out.update({
        "body": post.body,
        "meta_title": post.meta_title,
        "meta_description": post.meta_description,
        "focus_keyword": post.focus_keyword,
        "secondary_keywords": post.secondary_keywords or [],
        "canonical_url": post.canonical_url,
        "archetype": post.archetype,
    })
    return out


def _categories_by_id(db: Session) -> dict[uuid.UUID, BlogCategory]:
    """Every category row, keyed by id.

    Deliberately not filtered by locale even though categories are per-locale
    now: this map is only ever indexed by a post's own `category_id`, so it
    already returns that post's own language edition. Filtering here would only
    turn a mislabelled row into a missing category on the card.
    """
    return {c.id: c for c in db.scalars(select(BlogCategory)).all()}


@router.post("/list")
def list_posts(body: ListBody, db: Session = Depends(db_session)):
    conditions = [BlogPost.locale == body.locale, visible_filter()]

    if body.category:
        # Scoped to the requested locale: `spss` is one row per locale, and
        # /blog/en/chu-de/spss must filter on the English row's id, not on
        # whichever of the two the database happened to return first.
        category = db.scalar(select(BlogCategory).where(
            BlogCategory.locale == body.locale, BlogCategory.slug == body.category))
        if category is None:
            # An unknown category is an empty page, not an error: the route is
            # public and a 404 here would let anyone probe which slugs exist.
            return {"posts": [], "total": 0, "page": body.page, "page_size": body.page_size}
        conditions.append(BlogPost.category_id == category.id)

    if body.q and body.q.strip():
        needle = f"%{body.q.strip()}%"
        conditions.append(or_(
            BlogPost.title.ilike(needle),
            BlogPost.excerpt.ilike(needle),
            BlogPost.focus_keyword.ilike(needle),
        ))

    total = db.scalar(select(func.count()).select_from(BlogPost).where(*conditions)) or 0
    rows = db.scalars(
        select(BlogPost)
        .where(*conditions)
        .order_by(desc(BlogPost.published_at), desc(BlogPost.created_at))
        .offset((body.page - 1) * body.page_size)
        .limit(body.page_size)
    ).all()

    categories = _categories_by_id(db)
    return {
        "posts": [compact(p, categories.get(p.category_id)) for p in rows],
        "total": total,
        "page": body.page,
        "page_size": body.page_size,
    }


def _related(db: Session, post: BlogPost, categories: dict) -> list[dict]:
    """Up to five neighbours: same category first, then shared tags."""
    picked: list[BlogPost] = []
    seen = {post.id}

    if post.category_id is not None:
        picked = list(db.scalars(
            select(BlogPost)
            .where(BlogPost.locale == post.locale, visible_filter(),
                   BlogPost.category_id == post.category_id, BlogPost.id != post.id)
            .order_by(desc(BlogPost.published_at))
            .limit(MAX_RELATED)
        ).all())
        seen.update(p.id for p in picked)

    if len(picked) < MAX_RELATED and post.tags:
        tags = {str(t).lower() for t in post.tags}
        window = db.scalars(
            select(BlogPost)
            .where(BlogPost.locale == post.locale, visible_filter())
            .order_by(desc(BlogPost.published_at))
            .limit(RELATED_SCAN)
        ).all()
        for candidate in window:
            if len(picked) >= MAX_RELATED:
                break
            if candidate.id in seen:
                continue
            if tags & {str(t).lower() for t in (candidate.tags or [])}:
                picked.append(candidate)
                seen.add(candidate.id)

    return [compact(p, categories.get(p.category_id)) for p in picked]


def _translations(db: Session, post: BlogPost) -> list[dict]:
    """`[{locale, slug}]` for the other visible editions of this article.

    Keyed on `translation_key`, which every row carries: an original holds its
    own slug and a translation holds the original's, so one equality finds the
    set. Visible only, because pointing hreflang at a page that is still
    scheduled sends a crawler to a 404.
    """
    key = post.translation_key or post.slug
    rows = db.execute(
        select(BlogPost.locale, BlogPost.slug)
        .where(BlogPost.translation_key == key, BlogPost.id != post.id, visible_filter())
        .order_by(BlogPost.locale)
    ).all()
    return [{"locale": locale, "slug": slug} for locale, slug in rows]


@router.post("/get")
def get_post(body: GetBody, db: Session = Depends(db_session)):
    post = db.scalar(
        select(BlogPost).where(
            BlogPost.locale == body.locale, BlogPost.slug == body.slug, visible_filter())
    )
    if post is None:
        # Same 404 for "does not exist" and "not published yet", so the route
        # never becomes a preview of the publishing queue.
        raise HTTPException(404, detail={"error": {"code": "not_found",
                                                   "message": "post not found"}})

    categories = _categories_by_id(db)
    payload = full(post, categories.get(post.category_id))
    payload["related"] = _related(db, post, categories)
    # Every other visible edition of this same article, so the page can declare
    # hreflang. Without it the two language editions of one article are two
    # pages competing for one query and the crawler, not us, picks the winner.
    payload["translations"] = _translations(db, post)

    # Best effort: a view counter is not worth failing a page render over.
    try:
        post.views = (post.views or 0) + 1
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return payload


@router.get("/image/{key}")
def blog_image(key: str) -> Response:
    """Serve a post-body image. Public, unauthenticated, and a GET.

    THE SECOND GET IN THE API, and the exception is the same kind /health gets.
    CLAUDE.md's POST-only rule exists so there is always a body for the auth
    token to ride in; this route has no token to carry and could not use one if
    it did. It is the `src` of an <img> on a public page — the browser issues a
    GET, Googlebot issues a GET, and neither can be argued with. A POST here
    would mean no image ever loads.

    `key` comes off a public URL, so it is matched against a strict sha256 +
    known-extension pattern before it touches S3. The bucket also holds every
    student's private uploads under `users/<uid>/projects/...`; without this
    check the route would read any of them out on request. The prefix is joined
    here, never taken from the caller.

    Cached `immutable` for a year because the key IS the hash of the bytes: the
    url cannot come to mean something else, so there is nothing to revalidate.
    """
    import os  # noqa: PLC0415

    from .uploads import s3_from_env  # noqa: PLC0415

    if not _IMAGE_KEY.match(key):
        raise HTTPException(400, detail={"error": {"code": "bad_key",
                                                   "message": "not an image key"}})
    try:
        obj = s3_from_env().get_object(Bucket=os.environ.get("S3_BUCKET"),
                                       Key=f"{BLOG_IMAGE_PREFIX}{key}")
        body = obj["Body"].read()
    except Exception as e:  # noqa: BLE001
        # A missing object is the ordinary case (a deleted image, a stale url in
        # an old post) and must read as 404, not as a 500 that pages someone.
        raise HTTPException(404, detail={"error": {"code": "not_found",
                                                   "message": "image not found"}}) from e

    return Response(
        content=body,
        media_type=_IMAGE_CONTENT_TYPE[key.rsplit(".", 1)[1]],
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/categories")
def list_categories(body: CategoriesBody, db: Session = Depends(db_session)):
    counts = dict(db.execute(
        select(BlogPost.category_id, func.count())
        .where(BlogPost.locale == body.locale, visible_filter())
        .group_by(BlogPost.category_id)
    ).all())

    # One locale's categories, not every row: the whole point of the locale
    # column is that /blog/en never renders the Vietnamese hub names.
    rows = db.scalars(
        select(BlogCategory)
        .where(BlogCategory.locale == body.locale)
        .order_by(BlogCategory.sort_order, BlogCategory.slug)).all()
    return {"categories": [
        {**category_dict(c), "post_count": counts.get(c.id, 0)} for c in rows]}


@router.post("/sitemap")
def sitemap(body: SitemapBody, db: Session = Depends(db_session)):
    conditions = [visible_filter()]
    if body.locale:
        conditions.append(BlogPost.locale == body.locale)
    rows = db.execute(
        select(BlogPost.locale, BlogPost.slug, BlogPost.updated_at)
        .where(*conditions)
        .order_by(desc(BlogPost.updated_at))
        .limit(SITEMAP_LIMIT)
    ).all()
    return [{"locale": locale, "slug": slug, "updated_at": iso(updated_at)}
            for locale, slug, updated_at in rows]

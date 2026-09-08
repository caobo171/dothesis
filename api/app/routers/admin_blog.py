"""Admin writes for the blog.

There is no admin UI for this yet (design §18): the surface exists so the
content engine, a script, or a future editor all go through one code path that
runs seed validation and the duplicate guard. The CLI's `create` command runs
the same guard, so a post cannot enter the bank without passing it whichever
door it comes through.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..blog.guard import assert_no_duplicate
from ..blog.seeds import SeedError, category_index, upsert_from_seed, validate_seed
from ..db import db_session
from ..jwt_auth import AuthedBody
from ..models import BlogCategory, BlogPost
from .blog import MAX_PAGE_SIZE, compact, iso

router = APIRouter(prefix="/admin/blog", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class AdminListBody(AuthedBody):
    locale: str | None = None
    status: int | None = None
    q: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=MAX_PAGE_SIZE)


class UpsertBody(AuthedBody):
    """A seed (§12) plus the publishing fields a seed does not carry."""

    model_config = {"extra": "allow"}

    schema_: str = Field(default="dothesis-blog-seed/1", alias="schema")
    title: str
    slug: str
    locale: str = "vi"
    meta_title: str
    meta_description: str
    focus_keyword: str
    excerpt: str
    category: str
    archetype: str
    body: str
    secondary_keywords: list = Field(default_factory=list)
    tags: list = Field(default_factory=list)
    sibling_slugs: list = Field(default_factory=list)
    images: list = Field(default_factory=list)
    focus_keyword_volume: int | None = None
    canonical_url: str | None = None
    source_batch: str | None = None
    image_url: str | None = None
    reading_time: int | None = None
    duplicate_override_reason: str | None = None
    status: int | None = None
    published_at: datetime | None = None
    scheduled_at: datetime | None = None


class DeleteBody(AuthedBody):
    id: uuid.UUID


def _admin_view(post: BlogPost, category: BlogCategory | None) -> dict:
    out = compact(post, category)
    out.update({
        "status": post.status,
        "scheduled_at": iso(post.scheduled_at),
        "focus_keyword": post.focus_keyword,
        "focus_keyword_volume": post.focus_keyword_volume,
        "archetype": post.archetype,
        "source_batch": post.source_batch,
        "duplicate_override_reason": post.duplicate_override_reason,
    })
    return out


@router.post("/list")
def admin_list(body: AdminListBody, db: Session = Depends(db_session)):
    conditions = []
    if body.locale:
        conditions.append(BlogPost.locale == body.locale)
    if body.status is not None:
        conditions.append(BlogPost.status == body.status)
    if body.q and body.q.strip():
        needle = f"%{body.q.strip()}%"
        conditions.append(or_(BlogPost.title.ilike(needle), BlogPost.slug.ilike(needle),
                              BlogPost.focus_keyword.ilike(needle)))

    total = db.scalar(select(func.count()).select_from(BlogPost).where(*conditions)) or 0
    rows = db.scalars(
        select(BlogPost).where(*conditions)
        .order_by(desc(BlogPost.created_at))
        .offset((body.page - 1) * body.page_size)
        .limit(body.page_size)
    ).all()
    categories = {c.id: c for c in db.scalars(select(BlogCategory)).all()}
    return {"posts": [_admin_view(p, categories.get(p.category_id)) for p in rows],
            "total": total, "page": body.page, "page_size": body.page_size}


@router.post("/upsert")
def admin_upsert(body: UpsertBody, db: Session = Depends(db_session)):
    seed = body.model_dump(by_alias=True, exclude={"access_token"})
    # Publishing fields are not part of the seed schema; hold them back so the
    # validator sees exactly what a seed file would contain.
    status = seed.pop("status", None)
    published_at = seed.pop("published_at", None)
    scheduled_at = seed.pop("scheduled_at", None)

    try:
        seed = validate_seed(seed)
    except SeedError as e:
        raise HTTPException(422, detail={"error": {"code": "invalid_seed",
                                                   "message": str(e)}}) from e

    from ..blog.seeds import find_post  # noqa: PLC0415

    existing = find_post(db, seed["locale"], seed["slug"])
    verdict = assert_no_duplicate(db, seed, exclude_id=existing.id if existing else None)
    if verdict.blocked:
        raise HTTPException(409, detail={"error": {"code": "duplicate_intent",
                                                   "message": verdict.message}})

    # Keyed by (locale, slug): categories are per-locale, so a slug-keyed map
    # here would bind an English seed to whichever hub the query returned first.
    category_ids = category_index(db)
    action, post = upsert_from_seed(
        db, seed, category_ids, now=datetime.now(timezone.utc),
        status=status, published_at=published_at, scheduled_at=scheduled_at)

    payload = _admin_view(post, db.get(BlogCategory, post.category_id)
                          if post.category_id else None)
    payload["action"] = action
    # An overridden clash is reported even though it did not block, so whoever
    # called can see what they just published next to.
    payload["clashes"] = [{"slug": c.slug, "score": c.score, "focus": c.focus,
                           "intent": c.intent} for c in verdict.clashes]
    return payload


@router.post("/delete")
def admin_delete(body: DeleteBody, db: Session = Depends(db_session)):
    post = db.get(BlogPost, body.id)
    if post is None:
        raise HTTPException(404, detail={"error": {"code": "not_found",
                                                   "message": "post not found"}})
    db.delete(post)
    db.commit()
    return {"deleted": True, "id": str(body.id)}

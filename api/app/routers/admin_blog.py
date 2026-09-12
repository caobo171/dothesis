"""Admin writes for the blog.

The content engine, the CLI, and the /admin/blog editor all go through this one
code path, so seed validation and the duplicate guard run whichever door a post
comes through. The CLI's `create` command runs the same guard.

`list` returns listing cards and deliberately has no `body` (a page of them
would be ~200KB); `get` is the editor's read, and carries everything a form has
to round-trip. Editing through `list` alone would silently blank whatever the
card left out.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..blog.guard import assert_no_duplicate
from ..blog.seeds import SeedError, category_index, upsert_from_seed, validate_seed
from ..db import db_session
from ..jwt_auth import AuthedBody
from ..models import BlogCategory, BlogPost
from .blog import BLOG_IMAGE_PREFIX, MAX_PAGE_SIZE, compact, full, iso

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


class GetBody(AuthedBody):
    id: uuid.UUID


class CategoryListBody(AuthedBody):
    """No locale filter by default, unlike the public route.

    /blog/categories answers for ONE locale because a reader is on one edition
    of the hub. An operator is managing both editions at once and needs to see
    which slugs exist in which language — that is exactly the gap a per-locale
    read would hide.
    """

    locale: str | None = None


class CategoryUpsertBody(AuthedBody):
    locale: str = "vi"
    slug: str
    name: str
    display_name: str
    intro_md: str | None = None
    sort_order: int = 0


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


#: Web-safe formats only, and the extension is derived from this map rather
#: than from the filename — the filename is caller-supplied and is what a
#: ".png.svg" would ride in on.
_IMAGE_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

#: Generous for a screenshot, mean enough that nobody drops a 12MP camera JPEG
#: onto a page whose whole job is to load fast for Google.
_IMAGE_MAX_BYTES_DEFAULT = 4 * 1024 * 1024


def _image_max_bytes() -> int:
    import os  # noqa: PLC0415

    try:
        return int(os.environ.get("BLOG_IMAGE_MAX_BYTES") or _IMAGE_MAX_BYTES_DEFAULT)
    except ValueError:
        return _IMAGE_MAX_BYTES_DEFAULT


@router.post("/upload-image")
async def admin_upload_image(file: UploadFile = File(...)):
    """Store an image for a post body and return a permanent public url.

    The UPLOAD half of this was never the missing piece — routers/uploads.py has
    put bytes in S3 since the beginning. What did not exist is a way to read one
    back without an account: that path 302s to a 300-second presigned url behind
    an owner-or-admin check, and an <img> on a public post is fetched by
    anonymous readers and by Googlebot, neither of which has a token and both of
    which arrive long after 300 seconds. Hence the companion GET in blog.py.

    CONTENT-ADDRESSED. The key is the sha256 of the bytes, so re-uploading the
    same image is idempotent (no duplicate objects, same url) and a given url
    can never come to mean different bytes — which is what lets the read side
    serve it `immutable` for a year.

    Stored as-is, in the format it arrived in. Converting to webp would be
    smaller and is what the illustration library does, but that runs through
    Pillow, and Pillow is installed here only as an undeclared transitive
    dependency — a prod upload route that 500s the day something stops pulling
    it in is a bad trade for a few KB. Declare it first, then convert.
    """
    import hashlib  # noqa: PLC0415
    import os  # noqa: PLC0415

    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

    # Resolved through the module, not bound at import: uploads.s3_from_env is
    # the single seam both this route and blog.blog_image go through.
    from .uploads import s3_from_env  # noqa: PLC0415

    mime = (file.content_type or "").lower()
    if mime not in _IMAGE_EXT:
        raise HTTPException(415, detail={"error": {"code": "bad_mime", "message":
            f"unsupported image type: {mime or 'unknown'}; "
            "expected one of " + ", ".join(sorted(_IMAGE_EXT))}})

    body = await file.read()
    if not body:
        raise HTTPException(400, detail={"error": {"code": "empty_file",
                                                   "message": "the file is empty"}})
    limit = _image_max_bytes()
    if len(body) > limit:
        raise HTTPException(413, detail={"error": {"code": "too_large", "message":
            f"image is {len(body)} bytes; the limit is {limit}"}})

    key = f"{hashlib.sha256(body).hexdigest()}.{_IMAGE_EXT[mime]}"
    # run_in_threadpool for the same reason uploads.py does it: boto3 is
    # blocking, this route is async, and a single-worker API stalls entirely for
    # the duration of a call made straight on the event loop.
    await run_in_threadpool(
        s3_from_env().put_object,
        Bucket=os.environ.get("S3_BUCKET"),
        Key=f"{BLOG_IMAGE_PREFIX}{key}",
        Body=body,
        ContentType=mime,
    )
    # Root-relative, like the illustration library's `/img/blog/x.webp`. An
    # absolute origin in a post body bakes the environment into the row; the
    # two places that need one (JSON-LD, OG tags) already run every url through
    # absoluteUrl().
    return {"url": f"/api/v1/blog/image/{key}", "bytes": len(body), "content_type": mime}


@router.post("/get")
def admin_get(body: GetBody, db: Session = Depends(db_session)):
    """One post, with everything the editor form has to round-trip.

    `full()` already assembles the public detail payload; the admin extras ride
    on top of it the same way `_admin_view` puts them on top of a card. Built
    from the same two helpers on purpose — a hand-rolled dict here is how a
    field gets added to the model, shown in the form, and silently dropped on
    save.
    """
    post = db.get(BlogPost, body.id)
    if post is None:
        raise HTTPException(404, detail={"error": {"code": "not_found",
                                                   "message": "post not found"}})
    category = db.get(BlogCategory, post.category_id) if post.category_id else None
    out = full(post, category)
    out.update({
        "status": post.status,
        "scheduled_at": iso(post.scheduled_at),
        "source_batch": post.source_batch,
        "duplicate_override_reason": post.duplicate_override_reason,
    })
    # NOT returned, because the column does not exist: `sibling_slugs` is a
    # seed-time field consumed when the post is written and never persisted on
    # BlogPost. The editor must not offer it either — a form field that reads
    # back empty and saves nothing is worse than its absence.
    return out


@router.post("/options")
def admin_options(body: AuthedBody, db: Session = Depends(db_session)):
    """What the editor's selects are allowed to contain.

    `category_slugs` is the closed list of §6 — a seed naming anything else is
    rejected by validate_seed, so the form offers these and nothing else.
    `archetypes` has no constant behind it (it is free text in the seed schema),
    so the only honest suggestion list is what the bank already uses; the form
    offers them as a datalist rather than a select for that reason.
    """
    from ..blog.seeds import CATEGORY_SLUGS  # noqa: PLC0415

    archetypes = db.scalars(
        select(BlogPost.archetype).where(BlogPost.archetype.is_not(None))
        .distinct().order_by(BlogPost.archetype)
    ).all()
    return {"category_slugs": list(CATEGORY_SLUGS),
            "archetypes": [a for a in archetypes if a]}


@router.post("/categories/list")
def admin_categories(body: CategoryListBody, db: Session = Depends(db_session)):
    """Every category row, with how many posts sit in each.

    The count is what makes the delete button's refusal legible before it is
    pressed, so it is not filtered to visible posts the way the public route's
    is: a draft still blocks the delete.
    """
    counts = dict(db.execute(
        select(BlogPost.category_id, func.count()).group_by(BlogPost.category_id)
    ).all())
    conditions = [BlogCategory.locale == body.locale] if body.locale else []
    rows = db.scalars(
        select(BlogCategory).where(*conditions)
        .order_by(BlogCategory.locale, BlogCategory.sort_order, BlogCategory.slug)
    ).all()
    return {"categories": [
        {"id": str(c.id), "locale": c.locale, "slug": c.slug, "name": c.name,
         "display_name": c.display_name, "intro_md": c.intro_md,
         "sort_order": c.sort_order, "post_count": counts.get(c.id, 0)}
        for c in rows]}


@router.post("/categories/upsert")
def admin_category_upsert(body: CategoryUpsertBody, db: Session = Depends(db_session)):
    """Create or refresh ONE language edition of a hub.

    Keyed on (locale, slug), matching the table's own uniqueness: the English
    and Vietnamese editions of `spss` are two rows sharing a slug, and a
    slug-keyed write here would overwrite one with the other.

    The slug must come from CATEGORY_SLUGS. A category is supposed to exist
    only once its own name has measured search volume, and a row invented here
    would be a hub that no seed can ever point at — validate_seed would reject
    every post aimed at it. Adding a genuinely new category is a change to that
    list, not an operator action.
    """
    from ..blog.seeds import CATEGORY_SLUGS  # noqa: PLC0415

    if body.slug not in CATEGORY_SLUGS:
        raise HTTPException(422, detail={"error": {"code": "unknown_category", "message":
            f"unknown category {body.slug!r}; expected one of " + ", ".join(CATEGORY_SLUGS)}})

    row = db.scalars(
        select(BlogCategory).where(BlogCategory.locale == body.locale,
                                   BlogCategory.slug == body.slug)).first()
    if row is None:
        row = BlogCategory(locale=body.locale, slug=body.slug)
        db.add(row)
    row.name = body.name
    row.display_name = body.display_name
    row.intro_md = body.intro_md
    row.sort_order = body.sort_order
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "locale": row.locale, "slug": row.slug,
            "name": row.name, "display_name": row.display_name,
            "intro_md": row.intro_md, "sort_order": row.sort_order}


@router.post("/categories/delete")
def admin_category_delete(body: DeleteBody, db: Session = Depends(db_session)):
    """Remove an empty hub. Refuses while any post still points at it.

    blog_posts.category_id has no cascade behind it, so deleting an occupied
    row leaves every post in it pointing at nothing: the hub page 404s with its
    posts still inside, and the posts lose their category on every card. The
    operator must move or delete the posts first — which is a decision, not
    something this endpoint should make for them.
    """
    row = db.get(BlogCategory, body.id)
    if row is None:
        raise HTTPException(404, detail={"error": {"code": "not_found",
                                                   "message": "category not found"}})
    count = db.scalar(select(func.count()).select_from(BlogPost)
                      .where(BlogPost.category_id == row.id)) or 0
    if count:
        raise HTTPException(409, detail={"error": {"code": "category_not_empty", "message":
            f"{count} post(s) still point at this category; move or delete them first"}})
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": str(body.id)}


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

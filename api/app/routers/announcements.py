"""User-facing announcement fetch."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import Announcement, User

router = APIRouter(prefix="/announcements", tags=["announcements"])


def _serialize(a: Announcement) -> dict:
    return {
        "id": str(a.id), "kind": a.kind, "title": a.title, "body": a.body,
        "image_url": a.image_url, "cta_label": a.cta_label, "cta_url": a.cta_url,
    }


def _pick_one(db: Session, kind: str) -> Announcement | None:
    now = datetime.now(timezone.utc)
    stmt = (
        select(Announcement)
        .where(
            Announcement.kind == kind,
            Announcement.active.is_(True),
            or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
            or_(Announcement.ends_at.is_(None), Announcement.ends_at > now),
        )
        .order_by(desc(Announcement.created_at))
        .limit(1)
    )
    return db.scalar(stmt)


@router.post("/me")
def announcements_for_me(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    first = _pick_one(db, "first_login")
    banner = _pick_one(db, "login_banner")
    return {
        "first_login": _serialize(first) if first else None,
        "login_banner": _serialize(banner) if banner else None,
    }

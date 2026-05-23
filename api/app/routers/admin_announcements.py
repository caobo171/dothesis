"""Admin CRUD for announcements."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..models import Announcement

router = APIRouter(prefix="/admin/announcements", tags=["admin"], dependencies=[Depends(require_admin)])

ALLOWED_KINDS = {"first_login", "login_banner"}


class AnnouncementIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    image_url: str | None = None
    cta_label: str | None = Field(default=None, max_length=64)
    cta_url: str | None = None
    active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class AnnouncementPatch(BaseModel):
    kind: str | None = None
    title: str | None = None
    body: str | None = None
    image_url: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    active: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


def _serialize(a: Announcement) -> dict:
    return {
        "id": str(a.id), "kind": a.kind, "title": a.title, "body": a.body,
        "image_url": a.image_url, "cta_label": a.cta_label, "cta_url": a.cta_url,
        "active": a.active,
        "starts_at": a.starts_at.isoformat() if a.starts_at else None,
        "ends_at": a.ends_at.isoformat() if a.ends_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("")
def list_all(db: Session = Depends(db_session)):
    rows = db.scalars(select(Announcement).order_by(desc(Announcement.created_at))).all()
    return {"items": [_serialize(a) for a in rows], "total": len(rows), "page": 1, "page_size": len(rows)}


@router.post("", status_code=201)
def create(body: AnnouncementIn, db: Session = Depends(db_session)):
    if body.kind not in ALLOWED_KINDS:
        raise HTTPException(422, detail={"error": {"code": "bad_kind"}})
    a = Announcement(**body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.patch("/{ann_id}")
def patch(ann_id: uuid.UUID, body: AnnouncementPatch, db: Session = Depends(db_session)):
    a = db.get(Announcement, ann_id)
    if not a:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    for key, val in body.model_dump(exclude_unset=True).items():
        if key == "kind" and val not in ALLOWED_KINDS:
            raise HTTPException(422, detail={"error": {"code": "bad_kind"}})
        setattr(a, key, val)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.delete("/{ann_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(ann_id: uuid.UUID, db: Session = Depends(db_session)):
    a = db.get(Announcement, ann_id)
    if not a:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    db.delete(a)
    db.commit()
    return Response(status_code=204)

"""SP6: download endpoint for M5 export artifacts.

Mounted under /api/v1 by app/main.py only when ORCHESTRATOR_ENABLED=true.
Resolves the s3_key from the project's M5Output.export_artifacts and
302-redirects the browser to a fresh 5-minute signed URL.
"""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import ContextStore, Project, User
from ..routers.uploads import s3_from_env

router = APIRouter(tags=["exports"])


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    # Raise 404 (not 403) to avoid leaking project existence to non-owners.
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found"}},
        )
    return p


@router.get("/projects/{project_id}/exports/{filename}")
def download_export(
    project_id: uuid.UUID, filename: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """302-redirect to a fresh 5-minute signed URL for the requested artifact."""
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    m5 = (cs.m5_writing or {}) if cs else {}
    artifacts = m5.get("export_artifacts") or []
    expected_key = f"projects/{project_id}/exports/{filename}"
    # Only redirect if the artifact key is present — prevents guessing other keys.
    if not any(a.get("s3_key") == expected_key for a in artifacts):
        raise HTTPException(
            404, detail={"error": {"code": "artifact_not_found"}},
        )
    s3 = s3_from_env()
    signed_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["AWS_S3_BUCKET"], "Key": expected_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url=signed_url, status_code=302)

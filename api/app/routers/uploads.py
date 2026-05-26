"""PDF/text upload endpoints for M2 Literature Review (sub-project 2).

Uploads are project-scoped (shared across all threads of a project). On POST,
the file is stored in S3 and text is synchronously extracted via pdfminer.six
and cached to a sibling S3 object. M2 sub-graph's Phase 1 reads the list via
the orchestrator wrapper.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import PaperUpload, Project, User
from ..pdf_extract import extract_pdf_text

router = APIRouter(tags=["uploads"])

_ALLOWED_MIME = {"application/pdf", "text/plain"}
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024


def _max_bytes() -> int:
    return int(os.getenv("M2_UPLOAD_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))


def s3_from_env():
    """Indirection so tests can monkeypatch easily.

    Returns a raw boto3 S3 client built from environment variables, matching
    the put_object/get_object interface expected by the upload handler.
    """
    import boto3
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
    )


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404,
                            detail={"error": {"code": "not_found", "message": "project not found"}})
    return p


def _owned_upload(db: Session, user: User, upload_id: uuid.UUID) -> PaperUpload:
    up = db.get(PaperUpload, upload_id)
    if not up:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _owned_project(db, user, up.project_id)
    return up


class UploadOut(BaseModel):
    upload_id: uuid.UUID
    filename: str
    size_bytes: int
    mime_type: str
    page_count: int | None
    uploaded_at: Any


class UploadListItem(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    mime_type: str
    page_count: int | None
    uploaded_at: Any


@router.post("/projects/{project_id}/uploads", response_model=UploadOut)
async def upload_paper(project_id: uuid.UUID,
                       file: UploadFile = File(...),
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)):
    """Accept a PDF or text file, store in S3, extract text synchronously."""
    p = _owned_project(db, user, project_id)

    mime = file.content_type or "application/octet-stream"
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=415,
                            detail={"error": {"code": "bad_mime",
                                              "message": f"unsupported content type: {mime}"}})

    body = await file.read()
    if len(body) > _max_bytes():
        raise HTTPException(status_code=413,
                            detail={"error": {"code": "too_large",
                                              "message": f"file exceeds {_max_bytes()} bytes"}})

    upload_id = uuid.uuid4()
    bucket = os.environ.get("S3_BUCKET")
    s3_uri = f"s3://{bucket}/users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/{file.filename}"

    s3 = s3_from_env()
    s3.put_object(
        Bucket=bucket,
        Key=f"users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/{file.filename}",
        Body=body,
        ContentType=mime,
    )

    text = ""
    page_count = 0
    text_uri = None
    text_extracted_at = None
    if mime == "application/pdf":
        text, page_count = extract_pdf_text(body)
    else:
        try:
            text = body.decode("utf-8", errors="ignore")
            page_count = 1
        except Exception:
            text = ""

    if text:
        text_key = f"users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/extracted.txt"
        s3.put_object(Bucket=bucket, Key=text_key, Body=text.encode("utf-8"),
                      ContentType="text/plain")
        text_uri = f"s3://{bucket}/{text_key}"
        text_extracted_at = datetime.now(timezone.utc)

    row = PaperUpload(
        id=upload_id,
        project_id=project_id,
        filename=file.filename or "untitled",
        s3_uri=s3_uri,
        size_bytes=len(body),
        mime_type=mime,
        text_extracted_at=text_extracted_at,
        text_extract_uri=text_uri,
        page_count=page_count or None,
    )
    db.add(row); db.commit(); db.refresh(row)

    return UploadOut(
        upload_id=row.id, filename=row.filename, size_bytes=row.size_bytes,
        mime_type=row.mime_type, page_count=row.page_count,
        uploaded_at=row.uploaded_at,
    )


@router.get("/projects/{project_id}/uploads", response_model=list[UploadListItem])
def list_uploads(project_id: uuid.UUID,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)):
    _owned_project(db, user, project_id)
    return db.query(PaperUpload).filter_by(project_id=project_id) \
             .order_by(PaperUpload.uploaded_at.desc()).all()


@router.delete("/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: uuid.UUID,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    up = _owned_upload(db, user, upload_id)
    db.delete(up); db.commit()
    return None


@router.get("/uploads/{upload_id}/text", response_class=PlainTextResponse)
def get_upload_text(upload_id: uuid.UUID,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)):
    up = _owned_upload(db, user, upload_id)
    if not up.text_extract_uri:
        raise HTTPException(404, detail={"error": {"code": "no_text",
                                                    "message": "no extracted text for this upload"}})
    bucket = os.environ.get("S3_BUCKET")
    key = up.text_extract_uri.replace(f"s3://{bucket}/", "")
    s3 = s3_from_env()
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read().decode("utf-8", errors="ignore")

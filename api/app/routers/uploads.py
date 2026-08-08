"""PDF/text upload endpoints for M2 Literature Review (sub-project 2).

Uploads are project-scoped (shared across all threads of a project). On POST,
the file is stored in S3 and text is synchronously extracted via pdfminer.six
and cached to a sibling S3 object. M2 sub-graph's Phase 1 reads the list via
the orchestrator wrapper.
"""
from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import db_session
from ..auth_admin import readable_project as _readable_project
from ..deps import current_user, stream_user_factory
from ..models import PaperUpload, Project, User
from ..pdf_extract import extract_pdf_text

router = APIRouter(tags=["uploads"])
logger = logging.getLogger(__name__)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# Text-extractable upload formats. We only accept what we can pull real text
# from (so analysis never runs on an empty extraction): PDF, Word (.docx),
# plain text + markdown. Browsers sometimes send .docx as octet-stream on
# drag-drop, so the gate also accepts by extension (see _ALLOWED_EXT).
_ALLOWED_MIME = {"application/pdf", "text/plain", "text/markdown", _DOCX_MIME}
_ALLOWED_EXT = (".pdf", ".txt", ".md", ".markdown", ".docx")


def _extract_docx_text(body: bytes) -> tuple[str, int]:
    """Pull paragraph + table text from a .docx, IN DOCUMENT ORDER. Table rows
    are flattened into pipe rows so numbers inside result tables survive.
    Best-effort → ("", 0).

    Document order is the whole point. This used to emit every paragraph and
    then every table, which put a thesis's 17 result tables in one block at the
    very end, thousands of characters away from the sections that discuss them.
    Two things broke downstream:

      - the import's chapter split cuts on the final chapter's heading, so
        EVERY table landed on the chapter-5 side and left M4 — the analysis
        module — with no numbers at all. When the writer then regenerated
        chapter 5, the tables it had been handed were overwritten and the
        student's EFA loadings, item-total correlations and KMO tables were
        gone from the export.
      - the writer could not tell which table belonged to which section,
        because the layout said they all belonged at the end.

    The walk itself lives in agent.docx_extract, shared with the chat
    attachment path (agent.multimodal._textualize). One implementation, because
    the two had already drifted: uploads read tables and chat did not, so the
    same thesis was legible when imported and unreadable when attached.
    """
    from agent.docx_extract import extract_docx_text  # noqa: PLC0415
    return extract_docx_text(body), 0
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


def _readable_upload(db: Session, user: User, upload_id: uuid.UUID) -> PaperUpload:
    """The upload, if `user` may READ its project: owner or super admin.

    Split from `_owned_upload` for the same reason exports has the split: the
    uploads *list* takes the read gate (a super admin debugging a student's run
    needs the context panel to render), so a read of an individual file must
    take it too — otherwise the panel lists the file and the download button
    answers `project not found`. Deleting still goes through `_owned_upload`;
    an admin may look at a student's file, never destroy it.

    readable_project journals the admin access, which is the point: opening
    someone's uploaded thesis material is a privacy event.
    """
    up = db.get(PaperUpload, upload_id)
    if not up:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    _readable_project(db, user, up.project_id)
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
    fname = (file.filename or "").lower()
    # Accept by MIME, or by extension when the browser sent a generic
    # octet-stream (common for .docx on drag-drop).
    if mime not in _ALLOWED_MIME and not fname.endswith(_ALLOWED_EXT):
        raise HTTPException(status_code=415,
                            detail={"error": {"code": "bad_mime",
                                              "message": f"unsupported file type: {mime or fname}"}})

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
    if mime == "application/pdf" or fname.endswith(".pdf"):
        text, page_count = extract_pdf_text(body)
    elif mime == _DOCX_MIME or fname.endswith(".docx"):
        text, page_count = _extract_docx_text(body)
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

    # Mirror the upload into the agent's workspace so the v3 deep agent's
    # `read_file` and `parse_reference` tools can reach the file. The
    # workspace path matches chat_v3._workspace_dir; both write to it. We
    # write the RAW bytes (so `parse_reference` can PDF-extract directly)
    # and a sidecar `.txt` (so `read_file` gives the agent quick text
    # without paying for re-extraction every read). Best-effort —
    # mirroring failure should never break the upload route.
    try:
        from pathlib import Path as _P
        import tempfile as _tmp
        workspace = _P(os.getenv("JOB_WORKDIR_ROOT") or _tmp.gettempdir()) / "agent_projects" / str(project_id)
        (workspace / "uploads").mkdir(parents=True, exist_ok=True)
        safe_name = (file.filename or "untitled").replace("/", "_")
        (workspace / "uploads" / safe_name).write_bytes(body)
        if text:
            (workspace / "uploads" / f"{safe_name}.txt").write_text(text, encoding="utf-8")
    except Exception as _e:  # noqa: BLE001 — best-effort mirror
        pass

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


# Renamed from GET → POST .../uploads/list: POST .../uploads already creates an
# upload, so the list read needs a distinct path.
@router.post("/projects/{project_id}/uploads/list", response_model=list[UploadListItem])
def list_uploads(project_id: uuid.UUID,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)):
    # Readable, not owned: the chat layout calls this to fill the context panel,
    # so a super admin opening a student's thread to debug would otherwise get a
    # 404 here and a half-rendered page. Read-only — uploading and deleting
    # still require ownership below.
    _readable_project(db, user, project_id)
    return db.query(PaperUpload).filter_by(project_id=project_id) \
             .order_by(PaperUpload.uploaded_at.desc()).all()


@router.delete("/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: uuid.UUID,
                  user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    up = _owned_upload(db, user, upload_id)
    db.delete(up); db.commit()
    return None


@router.get("/uploads/{upload_id}/download")
def download_upload(
    upload_id: uuid.UUID,
    # GET-only (browser <a download>) — auth via a short-lived ?st= token
    # scoped to this exact upload, keeping the long-lived JWT out of the URL.
    user: User = Depends(stream_user_factory(
        lambda upload_id: f"project-upload:{upload_id}")),
    db: Session = Depends(db_session),
):
    """302-redirect to a fresh 5-minute signed URL for the uploaded file.

    Powers the Uploads section's download button. Mirrors the export download
    route: S3 presigned URL with ResponseContentDisposition so the browser
    saves the file under its original filename (not the opaque S3 key).
    """
    # Owner-or-admin: downloading is a read, and uploads/list beside it is
    # already readable — see _readable_upload.
    up = _readable_upload(db, user, upload_id)
    # s3_uri format: s3://<bucket>/users/<uid>/projects/<pid>/uploads/<uploadid>/<filename>
    if not (up.s3_uri or "").startswith("s3://"):
        raise HTTPException(404, detail={"error": {"code": "no_s3_uri"}})
    _, _, rest = up.s3_uri.partition("s3://")
    bucket, _, key = rest.partition("/")
    if not (bucket and key):
        raise HTTPException(500, detail={"error": {"code": "bad_s3_uri"}})
    s3 = s3_from_env()
    signed_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key,
                "ResponseContentDisposition":
                    f'attachment; filename="{up.filename}"'},
        ExpiresIn=300,
    )
    return RedirectResponse(url=signed_url, status_code=302)


@router.post("/uploads/{upload_id}/text", response_class=PlainTextResponse)
def get_upload_text(upload_id: uuid.UUID,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)):
    # Same read gate as the download beside it — the panel's text preview must
    # not 404 for an admin who can already see the file listed.
    up = _readable_upload(db, user, upload_id)
    if not up.text_extract_uri:
        raise HTTPException(404, detail={"error": {"code": "no_text",
                                                    "message": "no extracted text for this upload"}})
    bucket = os.environ.get("S3_BUCKET")
    key = up.text_extract_uri.replace(f"s3://{bucket}/", "")
    s3 = s3_from_env()
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read().decode("utf-8", errors="ignore")

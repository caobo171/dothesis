"""PDF/text upload endpoints for M2 Literature Review (sub-project 2).

Uploads are project-scoped (shared across all threads of a project). On POST,
the file is stored in S3 and text is synchronously extracted via pdfminer.six
and cached to a sibling S3 object. M2 sub-graph's Phase 1 reads the list via
the orchestrator wrapper.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import db_session
from ..auth_admin import readable_project as _readable_project
from ..deps import current_user, stream_user_factory
from ..models import PaperUpload, Project, User
from ..pdf_extract import extract_pdf_text
from ..http_headers import content_disposition
from ..workspace import workspace_dir

router = APIRouter(tags=["uploads"])
logger = logging.getLogger(__name__)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLS_MIME = "application/vnd.ms-excel"
# What we accept, and why each group is here:
#
#   documents — PDF, Word, plain text, markdown. We can pull real text out, so
#     analysis never runs on an empty extraction.
#   datasets  — .csv/.xlsx/.xls/.sav. NOT text-extractable, and deliberately so:
#     the value of a dataset is that `agent/tools/stats.py` can compute on it
#     off the workspace mirror below. What we cache is a profile (see
#     agent.data_profile), not the numbers. These used to 415 even though the
#     M4 skill text asks the student to upload exactly them.
#   results   — .htm/.html, the SmartPLS/SPSS results export that
#     agent/tools/output_parse.py parses.
#
# Browsers report these types inconsistently (.docx and .sav both arrive as
# octet-stream on drag-drop), so the gate accepts by extension too.
_ALLOWED_MIME = {
    "application/pdf", "text/plain", "text/markdown", _DOCX_MIME,
    "text/csv", "application/csv", _XLSX_MIME, _XLS_MIME,
    "text/html", "application/x-spss-sav",
}
_ALLOWED_EXT = (".pdf", ".txt", ".md", ".markdown", ".docx",
                ".csv", ".xlsx", ".xls", ".sav", ".htm", ".html")


_MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
             "image/bmp": "bmp", "image/tiff": "tif", "image/webp": "webp"}


def _figure_filename(entry: dict) -> str:
    """`hinh-04.png` — zero-padded so a directory listing sorts by page."""
    ext = _MIME_EXT.get(str(entry.get("mime") or "").lower(), "png")
    return f"hinh-{int(entry['figure']):02d}.{ext}"


def _extract_docx_text(body: bytes, *, stem: str = "") -> tuple[str, int, list]:
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
    images: list = []
    text = extract_docx_text(body, image_sink=images)
    # Name the file each figure came from, inline in the sidecar the agent
    # reads. Without this the agent knows a table was transcribed but not which
    # screenshot backs it, and Chapter 4 can only rebuild the table in markdown
    # — which reads as retyped rather than as SmartPLS output.
    for entry in images:
        entry["relpath"] = f"uploads/{stem}.img/{_figure_filename(entry)}"
        text = text.replace(
            f"[Hình {entry['figure']}]",
            f"[Hình {entry['figure']}] (ảnh gốc: {entry['relpath']})", 1)
    return text, 0, images


def is_dataset(filename: str) -> bool:
    """Delegates to agent.data_profile so the API and the chat attachment path
    agree on what counts as a dataset — the same sharing docx_extract does."""
    from agent.data_profile import is_dataset as _is_dataset  # noqa: PLC0415
    return _is_dataset(filename)


def profile_dataset(body: bytes, filename: str) -> str:
    from agent.data_profile import profile_dataset as _profile  # noqa: PLC0415
    return _profile(body, filename)
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024

# Cached extractions produced BEFORE this moment are not reused, however
# byte-identical the file is. A cached transcription is only as good as the
# model that made it, and gemini-2.5-flash — the vision sidecar until
# 2026-09-10 — mis-assigned all five outer loadings on a real SmartPLS path
# diagram and dropped one entirely. Re-uploading is how a student fixes a bad
# read, so dedupe must not hand the same wrong numbers straight back.
#
# BUMP THIS whenever the vision model or the extraction prompt changes. It is a
# constant rather than a column because the alternative — recording the model
# on every row — is a migration to answer a question this one line answers.
#
# The TIME matters, not just the date: the swap to gemini-3.5-flash-lite landed
# ~16:00 UTC, and the newest extraction made by the old model was 11:49 UTC the
# SAME DAY. A midnight epoch would have called all seventeen of those stale
# rows trustworthy and handed their wrong numbers back on re-upload — which is
# the precise failure this constant exists to prevent.
#
# 2026-09-11: the OUTPUT changed, not the model. Extraction now also saves each
# transcribed screenshot to `uploads/<name>.img/` and labels it in the sidecar
# ("[Hình 4] (ảnh gốc: …)"), which is how Chapter 4 embeds the student's real
# SmartPLS table instead of rebuilding it. Every sidecar cached before this has
# neither, and reusing one leaves the feature silently off for that upload — so
# the same rule applies as for a model swap.
_EXTRACTION_EPOCH = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def _extract_upload_text(body: bytes, mime: str, fname: str,
                         filename: str) -> tuple[str, int, list]:
    """(text, page_count, images) for one uploaded file. Pure and blocking — it
    is the slow half of this route (vision calls, pdfminer, OCR), so the caller
    hands it to a worker thread rather than running it on the event loop.

    `images` is the transcribed screenshots a .docx carried, for the caller to
    mirror into the workspace; every other type returns [].
    """
    if mime == "application/pdf" or fname.endswith(".pdf"):
        # Ingest: a scanned or screenshot-built PDF must not cache as empty text.
        text, pages = extract_pdf_text(body, ocr_if_hollow=True)
        return (text, pages, [])
    if mime == _DOCX_MIME or fname.endswith(".docx"):
        return _extract_docx_text(body, stem=(filename or "untitled").replace("/", "_"))
    if is_dataset(fname):
        # A dataset is not a document. Decoding .xlsx (a ZIP) or .sav as UTF-8
        # cached archive mojibake as the student's "data", which import_route
        # then handed to the model. Cache the variable view instead — shape,
        # columns, a few rows — and let the stats tools compute on the real file
        # mirrored into the workspace.
        return (profile_dataset(body, filename or "dataset"), 0, [])
    try:
        return (body.decode("utf-8", errors="ignore"), 1, [])
    except Exception:  # noqa: BLE001
        return ("", 0, [])


def _reusable_extraction(db: Session, project_id: uuid.UUID, body: bytes,
                         filename: str, workspace) -> PaperUpload | None:
    """A previous upload of these EXACT bytes whose extraction we can reuse.

    Identity is established against the workspace mirror rather than a stored
    hash: the mirror is where the prior upload's raw bytes already live, and
    this route is already committed to it for everything downstream, so it
    settles content-equality without a schema change.

    Deliberately narrow. Filename and size prune the candidates cheaply, the
    hash decides, and `_EXTRACTION_EPOCH` throws out anything read by a model
    we no longer trust. Anything unexpected returns None, which just means
    "extract it again" — the safe direction.
    """
    if workspace is None:
        return None
    safe_name = (filename or "untitled").replace("/", "_")
    mirror = workspace / "uploads" / safe_name
    try:
        if not mirror.exists():
            return None
        if hashlib.sha256(mirror.read_bytes()).digest() != hashlib.sha256(body).digest():
            return None
    except Exception:  # noqa: BLE001 — an unreadable mirror is not an error here
        return None
    return (db.query(PaperUpload)
              .filter(PaperUpload.project_id == project_id,
                      PaperUpload.filename == filename,
                      PaperUpload.size_bytes == len(body),
                      PaperUpload.text_extract_uri.isnot(None),
                      PaperUpload.text_extracted_at >= _EXTRACTION_EPOCH)
              .order_by(PaperUpload.uploaded_at.desc())
              .first())


def _inline_content_disposition(filename: str) -> str:
    """Build an HTTP-safe inline filename, including Unicode names.

    Starlette serializes response headers as Latin-1, so putting a Vietnamese
    filename directly in ``filename="..."`` raises before any bytes are sent.
    RFC 5987's ``filename*`` keeps the real UTF-8 name while the ASCII fallback
    remains compatible with older clients.
    """
    return content_disposition(filename, "inline")


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


# KNOWN COST: this route extracts text INSIDE the request. For a .docx that
# means agent.docx_extract vision-transcribes every pasted screenshot — up to 25
# sequential model calls — so a SmartPLS results document (which is nothing but
# result screenshots) can hold the POST open for minutes. The composer now waits
# on it visibly rather than dropping the file (web ChatInput.UPLOAD_WAIT_MS), but
# the real fix is to return the upload row immediately and extract in a job the
# client polls. Until then, do not tighten the client-side timeout.
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

    # Every blocking call below goes through run_in_threadpool. This route is
    # `async def`, so boto3 and the extraction were running ON the event loop:
    # a single-worker API (which is exactly what dev.sh starts) froze entirely
    # for the duration — 99 seconds, measured, on a results .docx — and every
    # other request behind it, not just this upload, waited.
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

    s3 = s3_from_env()
    await run_in_threadpool(
        s3.put_object,
        Bucket=bucket,
        Key=f"users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/{file.filename}",
        Body=body,
        ContentType=mime,
    )

    # Resolve the workspace BEFORE the mirror below is written: the mirror is
    # what tells us whether we have read these exact bytes before, and writing
    # first would compare the file against itself.
    try:
        workspace = workspace_dir(project_id)
    except Exception:  # noqa: BLE001 — no workspace just means no dedupe
        workspace = None

    text = ""
    page_count = 0
    text_uri = None
    text_extracted_at = None
    # On a reuse the screenshots are already mirrored beside the cached sidecar,
    # so there is nothing to write — but the name still has to be bound.
    images: list = []

    reuse = _reusable_extraction(db, project_id, body, file.filename or "untitled", workspace)
    if reuse is not None:
        # Same bytes, already read, read recently enough to trust. Point at the
        # existing extraction instead of buying it twice. A fresh row and id
        # still get created — re-uploading means "use this one", and collapsing
        # the two would make a deliberate re-upload look like a no-op.
        text_uri = reuse.text_extract_uri
        text_extracted_at = reuse.text_extracted_at
        page_count = reuse.page_count or 0
        logger.info("upload %s reuses the extraction cached on %s (%s)",
                    upload_id, reuse.id, file.filename)
    else:
        text, page_count, images = await run_in_threadpool(
            _extract_upload_text, body, mime, fname, file.filename or "")

    if text:
        text_key = f"users/{p.user_id}/projects/{project_id}/uploads/{upload_id}/extracted.txt"
        await run_in_threadpool(
            s3.put_object, Bucket=bucket, Key=text_key,
            Body=text.encode("utf-8"), ContentType="text/plain")
        text_uri = f"s3://{bucket}/{text_key}"
        text_extracted_at = datetime.now(timezone.utc)

    # Mirror the upload into the agent's workspace so the v3 deep agent's
    # `read_file` and `parse_reference` tools can reach the file. We write the
    # RAW bytes (so `parse_reference` can PDF-extract directly) and a sidecar
    # `.txt` (so `read_file` gives the agent quick text without paying for
    # re-extraction every read). Best-effort — mirroring failure should never
    # break the upload route.
    #
    # Through workspace_dir(), not by hand. This line used to spell the path out
    # inline under a comment claiming it "matches chat_v3._workspace_dir" — and
    # it did, until the helper was fixed to stop resolving a relative
    # JOB_WORKDIR_ROOT against the calling process's cwd. The copy kept the old
    # behaviour, so the student's file went to api/var/jobs/… while every reader
    # looked in var/jobs/…, and a full run wrote a thesis with an empty Results
    # chapter over a dataset that was on disk the whole time.
    # `workspace` was resolved above, before the dedupe check read the mirror.
    try:
        (workspace / "uploads").mkdir(parents=True, exist_ok=True)
        safe_name = (file.filename or "untitled").replace("/", "_")
        (workspace / "uploads" / safe_name).write_bytes(body)
        # On a reuse `text` is empty and the sidecar is left exactly as it is —
        # it already holds this file's extraction, written by the upload that
        # actually paid for it. Blanking it here would delete the cache the
        # chat turn now reads (chat_v3._materialize_attachments).
        if text:
            (workspace / "uploads" / f"{safe_name}.txt").write_text(text, encoding="utf-8")
        # The screenshots the OCR pass transcribed, beside the sidecar that
        # names them. Chapter 4 embeds these originals rather than a table
        # rebuilt from the transcription — a supervisor recognises SmartPLS
        # output, and the transcription is lossy on tight crops besides.
        if images:
            img_dir = workspace / "uploads" / f"{safe_name}.img"
            img_dir.mkdir(parents=True, exist_ok=True)
            for entry in images:
                (img_dir / _figure_filename(entry)).write_bytes(entry["bytes"])
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
                    content_disposition(up.filename, "attachment")},
        ExpiresIn=300,
    )
    return RedirectResponse(url=signed_url, status_code=302)


@router.get("/uploads/{upload_id}/raw")
def raw_upload(
    upload_id: uuid.UUID,
    # Same GET-with-?st= shape as /download beside it: an <iframe> and a
    # fetch() cannot attach a JSON body, so auth rides a short-lived token
    # scoped to this upload rather than the long-lived JWT.
    user: User = Depends(stream_user_factory(
        lambda upload_id: f"project-upload:{upload_id}")),
    db: Session = Depends(db_session),
):
    """Stream the file itself, INLINE and same-origin — the preview path.

    /download 302s to a presigned S3 URL with `attachment` disposition, which
    is right for saving a file and wrong for showing one: `attachment` makes
    the browser download instead of render, and the cross-origin redirect puts
    the bytes behind S3's CORS policy, so a fetch() (which is how a .docx gets
    converted for display) fails on a setting we do not control from here.

    Proxying the bytes costs one hop for a file the student just uploaded —
    these are thesis documents, not media — and buys a PDF that renders in the
    browser's own viewer and a .docx that docx-preview can lay out client-side.
    """
    up = _readable_upload(db, user, upload_id)
    if not (up.s3_uri or "").startswith("s3://"):
        raise HTTPException(404, detail={"error": {"code": "no_s3_uri"}})
    _, _, rest = up.s3_uri.partition("s3://")
    bucket, _, key = rest.partition("/")
    if not (bucket and key):
        raise HTTPException(500, detail={"error": {"code": "bad_s3_uri"}})
    body = s3_from_env().get_object(Bucket=bucket, Key=key)["Body"].read()
    return Response(
        content=body,
        media_type=up.mime_type or "application/octet-stream",
        # Decision: filename* preserves Vietnamese names without asking
        # Starlette to encode non-Latin-1 characters in the response header.
        headers={"Content-Disposition": _inline_content_disposition(up.filename)},
    )


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

"""Mid-journey import route (POST-only, authed). Extracts the project's uploads server-side,
infers per-module slices, commits them as earned state in MODULES order, and lands focus on the
first not-imported module.

Why a distinct path: chat.py already owns POST /projects/{id}/import (the M2 artifact-commit
flow), so this uses /projects/{id}/mid-journey-import to avoid shadowing it.
"""
from __future__ import annotations
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..deps import current_user, db_session
from ..import_work import import_existing_work
from ..models import PaperUpload, Project, User
from agent.state import MODULES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["import"])


def _authorize(db: Session, user: User, project_id) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "forbidden", "message": "not your project"}})
    return p


def _load_project_uploads(db: Session, project_id) -> list[dict]:
    """Read each upload's already-extracted text from S3 (the uploads flow caches it at
    text_extract_uri). Returns [{filename, text}]; uploads with no extracted text are skipped.
    Reuses the exact fetch pattern from routers/uploads.py:get_upload_text."""
    from .uploads import s3_from_env  # noqa: PLC0415 — reuse the env-built S3 client
    bucket = os.environ.get("S3_BUCKET")
    rows = db.execute(
        select(PaperUpload).where(PaperUpload.project_id == project_id)
    ).scalars().all()
    out: list[dict] = []
    s3 = None
    for up in rows:
        if not up.text_extract_uri:
            continue
        try:
            s3 = s3 or s3_from_env()
            key = up.text_extract_uri.replace(f"s3://{bucket}/", "")
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8", errors="ignore")
        except Exception:
            # A single unreadable upload must not sink the whole import.
            logger.exception("import: could not read extracted text for %s", up.filename)
            continue
        out.append({"filename": up.filename, "text": body})
    return out


def _store_and_files(db: Session, project_id):
    """Return (DbProjectStateStore, files, language). Uploads are neutralized before inference so
    a malicious document can't inject instructions into the LLM classify/infer step."""
    from ..agent_state import DbProjectStateStore
    from ..routers.chat_v3 import _workspace_dir
    from agent.guardrails import neutralize_document_text
    files = []
    for f in _load_project_uploads(db, project_id):
        clean, _flags = neutralize_document_text(f.get("text") or "")
        files.append({"filename": f.get("filename", "?"), "text": clean})
    store = DbProjectStateStore(db.bind, project_id, _workspace_dir(project_id))
    lang = "vi"  # DoThesis students write in Vietnamese; inference prompts localize on this
    return store, files, lang


def _set_focus(db: Session, project_id, focus: str) -> None:
    db.execute(update(Project).where(Project.id == project_id).values(focus=focus))
    db.commit()


@router.post("/projects/{project_id}/mid-journey-import")
def import_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)):
    _authorize(db, user, project_id)
    store, files, language = _store_and_files(db, project_id)
    res = import_existing_work(files, language)
    imported: list[str] = []
    for module in MODULES:                        # MODULES order → no spurious downstream needs_review
        if module in res["slices"]:
            try:
                store.commit_slice(module, res["slices"][module],
                                   reason=f"imported from {res['evidence'].get(module, 'upload')}")
                imported.append(module)
            except Exception:
                logger.exception("import: commit %s failed", module)   # skip, don't report a false import
    # focus = first module NOT actually committed (use `imported`, not slices, so a failed commit
    # doesn't get skipped over and leave the student stranded past unfinished work).
    focus = next((m for m in MODULES if m not in imported), MODULES[-1])
    _set_focus(db, project_id, focus)
    return {"imported": imported, "ambiguous": res["ambiguous"],
            "unreadable": res["unreadable"], "focus": focus}

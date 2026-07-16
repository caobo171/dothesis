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
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..deps import current_user, db_session
from ..import_work import import_existing_work
from ..models import ContextStore as DbContextStore, PaperUpload, Project, User
from agent.state import DOWNSTREAM, MODULES, NON_CONTENT_KEYS, SLICE_OWNERSHIP

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
    # Hint for the activation card: which UPSTREAM modules are still empty and
    # could be reconstructed from what we just imported. Only modules strictly
    # below the highest imported one, still `locked` (no content), and in the
    # M1-M4 reconstructable set. Cheap (no LLM) — the actual inference is the
    # separate /reconstruct call so import latency stays unchanged.
    from orchestrator.artifacts import MODULE_TO_ARTIFACT
    status = store.load()["status"]
    to_reconstruct: list[str] = []
    if imported:
        top = max(MODULES.index(m) for m in imported)
        to_reconstruct = [m for m in MODULES[:top]
                          if m in MODULE_TO_ARTIFACT and status.get(m) == "locked"]
    return {"imported": imported, "ambiguous": res["ambiguous"],
            "unreadable": res["unreadable"], "focus": focus,
            "to_reconstruct": to_reconstruct}


@router.post("/projects/{project_id}/mid-journey-import/reconstruct")
def reconstruct_upstream_modules(project_id: str, user: User = Depends(current_user),
                                 db: Session = Depends(db_session)):
    """Phase 2 of mid-journey import: infer the missing UPSTREAM modules from the
    imported evidence and return them as CANDIDATES (nothing is persisted). The
    activation card renders these for the student to confirm/edit. Best-effort —
    any failure yields an empty list rather than sinking the flow."""
    _authorize(db, user, project_id)
    from .chat import _orch_context_store
    from orchestrator.backfill import reconstruct_upstream
    try:
        cs = _orch_context_store(db, project_id)
        # DoThesis students write in Vietnamese; localize the inferred candidates.
        reconstructed = reconstruct_upstream(cs, language="vi")
    except Exception:
        logger.exception("import: reconstruct_upstream failed for %s", project_id)
        reconstructed = []
    return {"reconstructed": reconstructed}


class ConfirmReconstructionBody(BaseModel):
    module: str
    slice: dict


@router.post("/projects/{project_id}/mid-journey-import/confirm")
def confirm_reconstruction(project_id: str, body: ConfirmReconstructionBody,
                           user: User = Depends(current_user),
                           db: Session = Depends(db_session)):
    """Commit a (possibly user-edited) reconstructed candidate as EARNED state.

    Split write: schema fields the module owns go through commit_slice (which
    drives module_status / focus / analytics / version history); the remaining
    schema fields are merged straight into the context_store column tagged
    `_source=reconstructed` with NO confirmed_at — the module lands `in_progress`
    (a reviewable starting point), never silently `done`. Downstream modules that
    were already started are preserved (not flagged needs_review), and focus is
    restored so confirming an earlier step doesn't yank the student backwards.
    """
    from orchestrator.artifacts import MODULE_TO_ARTIFACT
    module = body.module
    if module not in MODULE_TO_ARTIFACT:
        raise HTTPException(422, detail={"error": {"code": "unknown_module",
                            "message": f"cannot reconstruct {module}"}})
    _authorize(db, user, project_id)

    # Sanitize: never trust client _-markers or confirmed_at; keep only real
    # slice fields (owned ones + the schema's other fields).
    from orchestrator.backfill import _schema_for_slice
    from orchestrator.artifacts import _ARTIFACT_BY_KEY
    schema = _schema_for_slice(_ARTIFACT_BY_KEY[MODULE_TO_ARTIFACT[module]].slice)
    allowed = set(SLICE_OWNERSHIP[module]) | set(schema.model_fields)
    allowed.discard("confirmed_at")
    # NON_CONTENT_KEYS (e.g. `decisions`) are owned by every module so the
    # stores persist them, but they're system-generated audit bookkeeping —
    # never document content an import could legitimately reconstruct. Letting a
    # client send one would let it forge/clobber the very trail that exists to
    # be trustworthy, so strip them like any other junk key.
    allowed -= NON_CONTENT_KEYS
    clean = {k: v for k, v in body.slice.items()
             if k in allowed and not str(k).startswith("_")}
    if not clean:
        raise HTTPException(422, detail={"error": {"code": "empty_slice",
                            "message": "no valid fields to confirm"}})

    from ..agent_state import _MODULE_COLUMN, DbProjectStateStore
    from .chat_v3 import _workspace_dir
    store = DbProjectStateStore(db.bind, project_id, _workspace_dir(project_id))
    prev = store.load()
    prev_focus = prev["focus"]

    # 1. Non-owned schema fields → direct column merge (commit_slice can't carry
    #    them). Tag reconstructed; do NOT write confirmed_at.
    column = _MODULE_COLUMN[module]
    cs_row = db.get(DbContextStore, project_id)
    if cs_row is None:
        cs_row = DbContextStore(project_id=project_id)
        db.add(cs_row)
    merged = {**(getattr(cs_row, column) or {}), **clean, "_source": "reconstructed"}
    setattr(cs_row, column, merged)
    db.commit()

    # 2. Owned fields + status → commit_slice. status_overrides applied AFTER the
    #    downstream needs_review pass, so we preserve any already-started
    #    downstream module (e.g. the just-imported M4) instead of flagging it.
    owned = {k: v for k, v in clean.items() if k in SLICE_OWNERSHIP[module]}
    overrides = {module: "in_progress"}
    for down in DOWNSTREAM[module]:
        if prev["status"].get(down) not in (None, "locked"):
            overrides[down] = prev["status"][down]
    store.commit_slice(module, owned,
                       reason="reconstructed candidate confirmed by user",
                       status_overrides=overrides)

    # 3. Restore focus — confirming an upstream backfill must not move the student.
    _set_focus(db, project_id, prev_focus)
    return {"module": module, "status": "in_progress", "focus": prev_focus}

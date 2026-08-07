"""Mid-journey import route (POST-only, authed). Extracts the project's uploads server-side,
infers per-module slices, commits them as earned state in MODULES order, and lands focus on the
first not-imported module.

Why a distinct path: chat.py already owns POST /projects/{id}/import (the M2 artifact-commit
flow), so this uses /projects/{id}/mid-journey-import to avoid shadowing it.
"""
from __future__ import annotations
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..deps import current_user, db_session
from ..import_work import import_existing_work
from ..models import PaperUpload, Project, User
from agent.state import MODULES, SLICE_OWNERSHIP, strip_reconstruction_meta

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


def _store(db: Session, project_id):
    """The project's state store — the only write path for module state."""
    from ..agent_state import DbProjectStateStore
    from ..routers.chat_v3 import _workspace_dir
    return DbProjectStateStore(db.bind, project_id, _workspace_dir(project_id))


def _store_and_files(db: Session, project_id):
    """Return (DbProjectStateStore, files, language). Uploads are neutralized before inference so
    a malicious document can't inject instructions into the LLM classify/infer step."""
    from agent.guardrails import neutralize_document_text
    files = []
    for f in _load_project_uploads(db, project_id):
        clean, _flags = neutralize_document_text(f.get("text") or "")
        files.append({"filename": f.get("filename", "?"), "text": clean})
    lang = "vi"  # DoThesis students write in Vietnamese; inference prompts localize on this
    return _store(db, project_id), files, lang


def _surface_of(request: Request) -> str:
    """Which client started the run. Mirrors routers/tools.py's helper; kept
    local so the import route does not pull in the whole tools module."""
    return (request.headers.get("X-DoThesis-Surface") or "web").strip()[:16] or "web"


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
    # Hint for the activation card: which modules the reconstruction should try
    # to finish from what we just imported — everything up to AND INCLUDING the
    # highest imported module that isn't `done`, within the M1-M4 reconstructable
    # set. Cheap (no LLM) — the actual inference is the separate /reconstruct
    # call so import latency stays unchanged.
    #
    # `!= "done"` rather than `== "locked"`, and `top + 1` rather than `top`,
    # because the imported module is usually the INCOMPLETE one: a finished
    # thesis lands in M4 as raw `analysis_results` with no `analysis_outline`,
    # so under the old rule the module carrying the student's actual results
    # was the one module we refused to finish — and the agent then asked them
    # to plan an analysis they had already run.
    from orchestrator.artifacts import MODULE_TO_ARTIFACT
    status = store.load()["status"]
    to_reconstruct: list[str] = []
    if imported:
        top = max(MODULES.index(m) for m in imported)
        to_reconstruct = [m for m in MODULES[:top + 1]
                          if m in MODULE_TO_ARTIFACT and status.get(m) != "done"]
    return {"imported": imported, "ambiguous": res["ambiguous"],
            "unreadable": res["unreadable"], "focus": focus,
            "to_reconstruct": to_reconstruct}


@router.post("/projects/{project_id}/mid-journey-import/reconstruct")
def reconstruct_upstream_modules(project_id: str, request: Request,
                                 user: User = Depends(current_user),
                                 db: Session = Depends(db_session)):
    """Phase 2 of mid-journey import: infer the missing UPSTREAM modules from the
    imported evidence and SAVE them.

    They used to come back as unsaved candidates behind a per-module
    Confirm/Skip card. Nobody should have to re-approve a reconstruction of
    their own work before the product will count it: it lands as `done` and the
    student edits it by asking, in chat, like everything else. The activation
    card just shows what was saved.

    Best-effort throughout — a failed inference yields an empty list, and a
    failed commit on one module doesn't sink the rest.
    """
    _authorize(db, user, project_id)
    from .chat import _orch_context_store
    from agent.tools.backfill_tool import (  # noqa: PLC0415
        _language_of_existing_work, _move_final_chapter_to_m5,
    )
    from orchestrator.backfill import reconstruct_upstream
    store = _store(db, project_id)
    slices = store.load_full_context_store() or {}

    # Open a run row BEFORE the work so the screen can poll it. Grounding turned
    # this from a few seconds into a minute-plus, and an unexplained wait is
    # what makes a student reload the page — which pays for the whole
    # reconstruction a second time. Same mechanism humanize-docx already uses.
    from ..tool_billing import begin_tool_run, bump_progress, finish_tool_run  # noqa: PLC0415
    # Progress is telemetry. Opening the row must never be what fails an import
    # the student already paid for in wall-clock time, so a failure here costs
    # the progress bar and nothing else.
    try:
        run_id = begin_tool_run(db, user, tool="backfill-modules",
                                surface=_surface_of(request))
    except Exception:
        logger.exception("import: could not open a progress run")
        run_id = None

    def _progress(done: int, total: int, module: str | None) -> None:
        if run_id is not None:
            bump_progress(run_id, done=done, total=total)

    # Persist each module the MOMENT it is reconstructed, not after the walk.
    #
    # This used to collect everything and commit afterwards, so a run that was
    # cancelled, timed out, or died on the last module discarded every module
    # before it — a minute-plus of paid LLM work for nothing, and the student
    # started over from zero. reconstruct_upstream only targets modules that
    # aren't COMPLETE, so committing as we go is also what makes a re-run
    # RESUME: whatever landed is skipped instead of being paid for twice.
    #
    # Safe to commit out of MODULES order here (the walk runs M4→M1) because
    # commit_reconstructed preserves the status of downstream modules that had
    # already started — see agent/state.py's `overrides`. It is commit_slice,
    # not this, that propagates needs_review.
    saved: list[dict] = []
    reconstructed: list[dict] = []

    def _save_now(entry: dict) -> None:
        module = entry.get("module")
        if not module:
            return
        # Keyed by module, not appended blindly: M2 is handed over a SECOND time
        # once M1 exists and its citations can be searched for (see
        # reconstruct_upstream). That re-emit must UPDATE the saved M2, not show
        # the student two literature modules.
        reconstructed[:] = [e for e in reconstructed if e.get("module") != module]
        saved[:] = [s for s in saved if s.get("module") != module]
        reconstructed.append(entry)
        # A commit failure on one module must not take the others down: the
        # exception is swallowed here so reconstruct_upstream's _hand_over does
        # not have to be the thing that decides this module is lost.
        try:
            saved.append(store.commit_reconstructed(module, entry.get("candidate") or {}))
        except Exception:
            logger.exception("import: commit_reconstructed %s failed for %s", module, project_id)

    try:
        cs = _orch_context_store(db, project_id)
        # Was hardcoded "vi" on the assumption every student writes Vietnamese.
        # They don't — this is the route the /new screen calls, and an English
        # thesis came back reconstructed into Vietnamese. Read it off their own
        # work instead; the agent tool does the same.
        reconstruct_upstream(
            cs, language=_language_of_existing_work(slices) or "vi",
            on_progress=_progress, on_module=_save_now)
    except Exception:
        # Whatever _save_now already committed STAYS committed — that is the
        # point of the incremental commit above. Report what landed.
        logger.exception("import: reconstruct_upstream failed for %s", project_id)
    finally:
        # ALWAYS close the row. /runs/active answers "what is this user running
        # right now" from the newest row still marked running, so one import
        # left open would report itself as the live job forever and every later
        # document walk would poll its stale numbers. `ok` reflects whether any
        # module survived, not whether the walk finished cleanly — a run that
        # died after saving three modules did work for the student.
        finish_tool_run(run_id, ok=bool(saved))

    # Display order for the response; the commits themselves ran bottom-up.
    reconstructed.sort(key=lambda e: MODULES.index(e["module"]) if e["module"] in MODULES else 99)
    saved.sort(key=lambda s: MODULES.index(s["module"]) if s.get("module") in MODULES else 99)
    # A finished thesis arrives as one blob under m4_analysis, chapters 4 AND 5
    # together, so M5 receives nothing and stays locked behind work already
    # done. Declines on anything ambiguous — see chapter_split.
    moved = _move_final_chapter_to_m5(store, slices)

    # Hand M2's literature search off to a background process.
    #
    # The walk above already committed whatever the fast shallow search found —
    # a handful of real, on-topic, DOI-bearing papers, immediately. That is a
    # usable literature module, not a literature review. The deep planner is
    # what produces real coverage and it wants minutes, which is more than a
    # request has: run inline it timed out at 120s and everything it found was
    # thrown away.
    #
    # So the student gets the fast set now and the deep set when it lands,
    # instead of being made to choose. Its own run row, so the screen can poll
    # this search separately from the reconstruction that just finished.
    cite_run_id = None
    try:
        from ..job_runner import spawn_citation_search  # noqa: PLC0415
        cite_run_id = begin_tool_run(db, user, tool="citation-search",
                                     surface=_surface_of(request))
        if not spawn_citation_search(project_id, cite_run_id):
            # Nothing launched, so nothing will ever close that row — and a row
            # left running makes /runs/active report a dead job as live.
            finish_tool_run(cite_run_id, ok=False)
            cite_run_id = None
    except Exception:
        logger.exception("import: could not start the citation search for %s", project_id)
        cite_run_id = None

    # No _set_focus here: commit_reconstructed already advanced focus past the
    # steps it completed, and the store's own save writes Project.focus.
    return {"reconstructed": reconstructed, "saved": saved,
            "final_chapter_moved": moved,
            # The client polls /runs/{id}/progress with this while the POST is
            # still in flight.
            "run_id": run_id,
            # Still going after this response returns — the deep literature
            # search. Non-null means M2's citations will improve on their own.
            "citation_run_id": cite_run_id,
            "focus": store.load()["focus"]}


class ConfirmReconstructionBody(BaseModel):
    module: str
    slice: dict


@router.post("/projects/{project_id}/mid-journey-import/confirm")
def confirm_reconstruction(project_id: str, body: ConfirmReconstructionBody,
                           user: User = Depends(current_user),
                           db: Session = Depends(db_session)):
    """Write a user-supplied version of a reconstructed module's slice.

    Reconstructions save themselves now (see /reconstruct), so this is no longer
    the gate they pass through — it's the EDIT path: the student (or a partner
    client) sends corrected fields for a module that was backfilled, and they
    land through the same store write as the original, with the same done /
    focus / downstream-preservation semantics.
    """
    from orchestrator.artifacts import MODULE_TO_ARTIFACT
    module = body.module
    if module not in MODULE_TO_ARTIFACT:
        raise HTTPException(422, detail={"error": {"code": "unknown_module",
                            "message": f"cannot reconstruct {module}"}})
    _authorize(db, user, project_id)

    # Sanitize: this is the one path where the slice comes from a CLIENT, so
    # narrow it to real slice fields (owned ones + the schema's other fields)
    # before it reaches the store. strip_reconstruction_meta drops the rest
    # (_-markers, confirmed_at, the `decisions` audit trail).
    from orchestrator.backfill import _schema_for_slice
    from orchestrator.artifacts import _ARTIFACT_BY_KEY
    schema = _schema_for_slice(_ARTIFACT_BY_KEY[MODULE_TO_ARTIFACT[module]].slice)
    allowed = set(SLICE_OWNERSHIP[module]) | set(schema.model_fields)
    clean = {k: v for k, v in strip_reconstruction_meta(body.slice).items()
             if k in allowed}
    if not clean:
        raise HTTPException(422, detail={"error": {"code": "empty_slice",
                            "message": "no valid fields to confirm"}})

    return _store(db, project_id).commit_reconstructed(
        module, clean, reason="reconstructed slice edited by user")

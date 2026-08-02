"""Partner report endpoint — service-to-service ("Powered by DoThesis").

Rebuilt as a headless CLIENT of the deep agent (convergence spec §3): the upload
becomes a REAL project row + a Job running `run_headless` in a subprocess, then
the shared compose/export path renders the requested report shape. The old
partner_report_service was a third generation engine — private prompts, a private
compose loop, zero tools and zero skills. Going through build_agent is what hands
partner all ~20 tools and all 8 skills, which is the entire point of this switch.

The multipart contract (shared X-Partner-Token secret, POST-only) is unchanged.
TWO breaking changes to the RESPONSES, both deliberate:

1. `progress_token` is now MINTED here and RETURNED, never accepted:
   jobs.partner_token is UNIQUE and partner auth is one global shared secret with
   no partner identity, so a caller-chosen value is both a collision (500 at
   INSERT) and a read capability anyone holding the shared secret could guess.
2. /partner/report/progress kept its SHAPE but changed the MEANING of phase /
   total / done / current — see that endpoint's docstring. It shipped
   undisclosed; a partner rendering the old semantics gets wrong labels rather
   than an error, which is why it is written down there in full.

Progress now reads the Job row instead of an in-memory dict, so it survives
restarts and works across API processes.

Auth is a single shared secret (settings.partner_api_token). Empty secret ->
the endpoint 401s on every call, so it stays closed until explicitly enabled.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.state import MODULES

from .. import job_runner
from .. import partner_run as prun
from ..agent_state import DbProjectStateStore
from ..db import db_session
from ..models import Job, JobEvent, Project
from ..settings import get_settings
from ..workspace import workspace_dir
from .uploads import s3_from_env

logger = logging.getLogger(__name__)

router = APIRouter(tags=["partner"])

# Analysis PDFs are typically small; cap defensively so a partner can't stream a
# giant file into the LLM path.
_MAX_BYTES = 25 * 1024 * 1024
_ALLOWED_MIME = {
    "application/pdf",
    "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",
}

# Module count the progress poll reports against — IMPORTED, not restated. This
# is the literal denominator headless_entry's hook divides by (`done_n /
# len(MODULES)`), so a local `= 5` is a second copy of someone else's constant:
# add M6 and this endpoint reports progress against the wrong total, out of a
# file that never mentions modules. `done/total` only means one thing if there is
# one definition of total.
_TOTAL_MODULES = len(MODULES)


def _require_partner(x_partner_token: str | None) -> None:
    """Constant-time check of the shared partner secret. 401 on any mismatch."""
    expected = get_settings().partner_api_token
    if not expected or not x_partner_token or not hmac.compare_digest(x_partner_token, expected):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "bad_partner_token", "message": "invalid partner token"}},
        )


class PartnerReportOut(BaseModel):
    pages: int
    depth: str
    chapters: list[str]
    sections: list[str]
    pdf_url: str | None
    docx_url: str | None
    pdf_key: str | None = None
    docx_key: str | None = None
    # Server-minted. Additive to the old response: the caller used to CHOOSE this
    # value and send it up, which the UNIQUE index turned into a 500 waiting to
    # happen. Partners now read it back from here to poll /partner/report/progress.
    progress_token: str | None = None
    powered_by: str = "DoThesis"


async def _wait_for_job(engine, job_id: uuid.UUID, timeout_s: int) -> str:
    """Poll the Job row until terminal — the endpoint stays synchronous (the
    existing partner contract: one long call, progress polled alongside), but
    completion is now observed through the same DB rows the monitor writes, so it
    works across processes and restarts."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while True:
        with Session(engine) as s:
            j = s.get(Job, job_id)
            status = j.status if j else "failed"
        if status in {"done", "failed", "canceled"}:
            return status
        if loop.time() > deadline:
            return "timeout"
        await asyncio.sleep(2.0)


def _job_done_meta(engine, job_id: uuid.UUID) -> dict:
    with Session(engine) as s:
        ev = s.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.type == "job_done")
            .order_by(JobEvent.id.desc())
        ).first()
        return dict(ev.meta_json or {}) if ev else {}


def _job_error(engine, job_id: uuid.UUID) -> dict:
    """The last error event's stable code + message, if the run refused rather
    than crashed. run_partner_export's gate lives in the SUBPROCESS, so its
    ReportError.code travels here as event meta_json (headless_entry) — there is
    no in-process exception for the endpoint to catch."""
    with Session(engine) as s:
        ev = s.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.type == "error")
            .order_by(JobEvent.id.desc())
        ).first()
        if ev is None:
            return {}
        return {"code": (ev.meta_json or {}).get("code"), "message": ev.text or ""}


def _job_current_activity(db: Session, job_id: uuid.UUID) -> str | None:
    """The run's most recent activity line, for the progress poll's `current`.

    headless_entry's progress hook already emits one activity event per tool
    call, so the live "what is it doing" string exists — it just wasn't being
    read. None until the first tool runs, which is honest: nothing to report yet.
    """
    ev = db.scalars(
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.type == "activity")
        .order_by(JobEvent.id.desc())
    ).first()
    return (ev.text or None) if ev is not None else None


def _parse_module(name: str, raw: str | None) -> dict | None:
    """Parse an optional module JSON up front so a malformed SHAPE is a clean 422
    rather than a module that silently never arrives.

    Scope note: this guarantees the envelope, not the contents. Individual KEYS
    are still dropped downstream — seed_partner_store writes through commit_slice
    and filters to each module's SLICE_OWNERSHIP, so a key sent to the wrong
    module (research_gaps under m1: it is M2-owned) or a key nothing owns is
    discarded. That is correct — ownership is the invariant the store is built on
    — but it is a drop, so seed_partner_store LOGS it instead of this docstring
    claiming a blanket "never a silent drop" it cannot deliver."""
    if not raw:
        return None
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(422, detail={"error": {"code": "bad_module_json",
                                                   "message": f"{name} must be valid JSON"}})
    if not isinstance(val, dict):
        raise HTTPException(422, detail={"error": {"code": "bad_module_json",
                                                   "message": f"{name} must be a JSON object"}})
    return val


@router.post("/partner/report", response_model=PartnerReportOut)
async def create_partner_report(
    # A report is routinely assembled from SEVERAL documents — an đề cương plus
    # an SPSS output to write chapters 4+5, or the handful of exports SmartPLS
    # produces. `files` is the current field; `file` is kept so an older partner
    # build (or an in-flight request during a rollout) keeps working, since the
    # two sides do not deploy atomically. Both may be sent; they concatenate.
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
    depth: str = Form("analysis_report"),
    # Optional comma-separated subset of intro,lit_review,methodology,results,
    # discussion,conclusion. When set it overrides `depth` (the "tick Chương N"
    # path). Empty/absent falls back to `depth`.
    chapters: str | None = Form(None),
    title: str | None = Form(None),
    # Optional free-text context the end user typed to steer the writing.
    notes: str | None = Form(None),
    language: str = Form("en"),
    # Optional caller-supplied M1/M2/M3 modules as JSON strings (the input
    # contract). Each present one seeds the project verbatim; missing ones are
    # left for the agent to reconstruct (backfill). Sent as form fields so they
    # ride alongside the file upload.
    m1: str | None = Form(None),
    m2: str | None = Form(None),
    m3: str | None = Form(None),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
):
    _require_partner(x_partner_token)

    uploads = [u for u in [*(files or []), *([file] if file else [])] if u is not None]
    if not uploads:
        raise HTTPException(422, detail={"error": {"code": "empty_file",
                                                   "message": "no file bytes"}})

    # (filename, bytes) in upload order. The size cap is now a TOTAL across the
    # set, not per file — otherwise N files each just under the limit would slip
    # through and blow the same budget the cap exists to protect.
    docs: list[tuple[str, bytes]] = []
    total_bytes = 0
    for up in uploads:
        if up.content_type and up.content_type not in _ALLOWED_MIME:
            raise HTTPException(
                415, detail={"error": {"code": "unsupported_media_type",
                                       "message": f"expected a PDF, got {up.content_type}"}})
        raw = await up.read()
        if not raw:
            raise HTTPException(422, detail={"error": {"code": "empty_file",
                                                       "message": "no file bytes"}})
        total_bytes += len(raw)
        if total_bytes > _MAX_BYTES:
            raise HTTPException(413, detail={"error": {"code": "file_too_large",
                                                       "message": f"max {_MAX_BYTES // (1024 * 1024)}MB total"}})
        docs.append((up.filename or "analysis.pdf", raw))

    chapter_list = [c.strip() for c in chapters.split(",") if c.strip()] if chapters else None
    m1_d, m2_d, m3_d = (_parse_module("m1", m1), _parse_module("m2", m2),
                        _parse_module("m3", m3))

    # Everything below fails fast BEFORE any row is created — a 422 must not
    # leave orphan projects/jobs behind.
    try:
        chapter_keys = prun.resolve_chapters(depth, chapter_list)
    except prun.ReportError as e:
        raise HTTPException(422, detail={"error": {"code": e.code, "message": e.message}})

    # Extract every document and concatenate under a filename banner, so the
    # agent can tell the đề cương from the SPSS output instead of reading one
    # undifferentiated blob. Files that yield no text are skipped rather than
    # fatal — one image-only scan alongside three good documents should not
    # sink the report; only an entirely unreadable SET is a 422.
    # The banner is added ONLY when there is more than one document. A single
    # upload must seed byte-identical text to before, so the common path's
    # prompt (and its golden) is untouched by multi-file support.
    parts: list[str] = []
    pages = 0
    multi = len(docs) > 1
    for name, raw in docs:
        one_text, one_pages = await run_in_threadpool(prun._extract_text, raw, name)
        pages += one_pages
        if one_text.strip():
            parts.append(f"===== FILE: {name} =====\n{one_text}" if multi else one_text)
    text = "\n\n".join(parts)
    if not text.strip():
        raise HTTPException(422, detail={"error": {"code": "no_extractable_text",
                                                   "message": "the file has no machine-readable text (image-only scan?)"}})
    if "results" in chapter_keys and not prun.pdf_looks_like_analysis(text):
        raise HTTPException(422, detail={"error": {"code": "insufficient_m4_data",
                                                   "message": "the uploaded file lacks the statistical analysis data "
                                                              "needed to write the Results (M4) chapter"}})

    # Real project row (system-owned) + workspace mirror + seeded store.
    sys_user = prun.ensure_partner_user(db)
    project = Project(user_id=sys_user.id,
                      name=(title or "Partner report").strip()[:200] or "Partner report",
                      language=language)
    db.add(project)
    db.commit()  # commit BEFORE seeding: the store opens its own connections

    workspace = workspace_dir(project.id)
    (workspace / "uploads").mkdir(parents=True, exist_ok=True)
    # Mirror the raw upload so agent tools (read_file / parse_reference) can open
    # it — same uploads/ convention chat uses. Seeding only carries the extracted
    # TEXT; the file itself has to exist for a tool to reach it.
    # Mirror every upload. os.path.basename strips any directory component a
    # client may have put in the filename — without it "../../x" would escape
    # the workspace. Same-named files get a numeric suffix so one cannot
    # silently overwrite another.
    seen_names: set[str] = set()
    for name, raw in docs:
        safe = os.path.basename(name) or "analysis.pdf"
        if safe in seen_names:
            stem, dot, ext = safe.rpartition(".")
            base = stem if dot else safe
            suffix = f".{ext}" if dot else ""
            n = 2
            while f"{base}-{n}{suffix}" in seen_names:
                n += 1
            safe = f"{base}-{n}{suffix}"
        seen_names.add(safe)
        (workspace / "uploads" / safe).write_bytes(raw)

    engine = db.get_bind()
    store = DbProjectStateStore(engine, project.id, workspace)
    # Seeding is sync DB I/O — keep it off the event loop.
    await run_in_threadpool(
        prun.seed_partner_store, store,
        analysis_text=text, m1=m1_d, m2=m2_d, m3=m3_d,
        title=title, notes=notes, language=language,
    )

    run = Job(paper_id=None, project_id=project.id, mode="partner",
              status="queued", partner_token=prun.mint_partner_token(),
              langgraph_thread_id=str(uuid.uuid4()))
    db.add(run)
    db.flush()
    progress_token = run.partner_token
    params = {
        "depth": depth, "chapters": chapter_list, "language": language,
        "max_turns": int(os.getenv("PARTNER_MAX_TURNS", "0")) or None,
        "wall_clock_s": int(os.getenv("PARTNER_WALL_CLOCK_S", "0")) or None,
    }
    job_runner.spawn_headless_run(db, run, params)

    status = await _wait_for_job(engine, run.id,
                                 timeout_s=int(os.getenv("PARTNER_REPORT_TIMEOUT_S", "2100")))
    if status != "done":
        # The readiness gate refusing is a 4xx about the INPUT, not a 5xx about
        # us: the partner has to change the payload, and report_failed would tell
        # them to retry the same one. Everything else (budget exhaustion / stall
        # / crash) stays a clean 502 — never a hollow report. The project +
        # partial state survive for inspection either way.
        err = _job_error(engine, run.id)
        if err.get("code") == "needs_data":
            raise HTTPException(422, detail={"error": {"code": "needs_data",
                                                       "message": err["message"]}})
        raise HTTPException(502, detail={"error": {"code": "report_failed",
                                                   "message": f"headless run ended: {status}"}})

    meta = _job_done_meta(engine, run.id)
    # A `done` run with no sections means the job_done event never arrived or
    # arrived empty — run_partner_export raises compose_failed rather than return
    # nothing, so this is the plumbing failing, not a legitimate empty report.
    # Defaulting to [] answered 200 with sections:[] and pdf_url:null, which is
    # the hollow-report-shaped success the old engine refused with compose_failed.
    if not meta.get("sections"):
        raise HTTPException(502, detail={"error": {"code": "compose_failed",
                                                   "message": "the run reported no composed sections"}})
    keys = meta.get("artifact_keys") or {}
    s3 = s3_from_env()

    def _sign(key):
        return prun._presign(s3, key) if key else None

    # F5: partner surface export completed. Headless (no user id) — best-effort.
    from ..analytics import emit
    emit("export_completed", None,
         {"scope": ",".join(chapter_list) if chapter_list else depth, "surface": "partner"})

    return {
        "pages": pages,
        "depth": depth,
        # POST-merge keys in BOTH branches. `chapter_keys` is the pre-merge
        # request, so falling back to it re-introduced exactly what 9b7d862
        # fixed: telling the partner about a `conclusion` chapter that exists in
        # no section. The rule has one home (merged_chapter_keys) — restating it
        # or bypassing it is how the two answers drift apart again.
        "chapters": meta.get("chapters") or prun.merged_chapter_keys(chapter_keys),
        "sections": meta["sections"],
        "pdf_url": _sign(keys.get("pdf")),
        "docx_url": _sign(keys.get("docx")),
        "pdf_key": keys.get("pdf"),
        "docx_key": keys.get("docx"),
        "progress_token": progress_token,
    }


class ProgressIn(BaseModel):
    progress_token: str


class ProgressOut(BaseModel):
    """Shape is unchanged; the MEANING of every field but `status` changed in
    Task 11 — see partner_report_progress's docstring for the field-by-field
    before/after. Kept as one block there so the contract has a single home."""
    status: str  # processing | done | error | unknown
    phase: str | None = None       # focus MODULE (M1..M5) — was research/compose/export
    total: int | None = None       # always len(MODULES) — was len(chapter_keys)
    done: int | None = None        # modules finished — was chapters composed
    current: str | None = None     # latest activity — was the chapter title


@router.post("/partner/report/progress", response_model=ProgressOut)
async def partner_report_progress(
    body: ProgressIn,
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
):
    """Poll live progress for an in-flight report — reads the Job the token maps
    to.

    !! BREAKING CONTRACT CHANGE (Task 11) — every field below changed meaning,
    and unlike the `progress_token` change it shipped undisclosed. A partner
    rendering the old shape gets wrong labels, not an error. Documented here so
    it is a known contract rather than a surprise:

      phase   — WAS "research" | "compose" | "export" (the old pipeline's three
                stages). NOW the focus MODULE: "M1".."M5". No value overlaps, so
                a switch on the old strings silently falls through to its
                default forever.
      total   — WAS len(chapter_keys): 3 for analysis_report, 5 for full_thesis,
                i.e. it moved with the request. NOW always len(MODULES) == 5.
                A caller that inferred the report shape from `total` is wrong.
      done    — WAS chapters composed. NOW modules finished. Same range for a
                full_thesis, different meaning; for an analysis_report the
                denominator changed too.
      current — WAS the chapter title being written ("Chapter 4 — Results").
                NOW the run's latest activity ("tool: research_scout"): the
                agent works a roadmap, not a fixed compose loop, so there is no
                chapter-in-progress to name. Still a human-readable "what is it
                doing right now" string, which is what the field was for.

    The granularity change itself is not the bug — module progress is the honest
    unit for an agent run, and it is durable across restarts and processes where
    the old in-memory dict was not.
    """
    _require_partner(x_partner_token)
    # No order_by: jobs.partner_token is UNIQUE (Task 9), so this matches at most
    # one row. Sorting one row is theatre that reads as "the newest of several".
    j = db.scalar(select(Job).where(Job.partner_token == body.progress_token))
    if j is None:
        return {"status": "unknown"}
    status = {"queued": "processing", "running": "processing",
              "done": "done"}.get(j.status, "error")
    return {"status": status, "phase": j.phase, "total": _TOTAL_MODULES,
            "done": int(round((j.progress or 0.0) * _TOTAL_MODULES)),
            "current": _job_current_activity(db, j.id)}

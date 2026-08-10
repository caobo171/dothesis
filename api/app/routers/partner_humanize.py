"""Partner humanize — the whole-document rewrite, reachable with the shared
partner secret instead of a student's session.

Why a separate surface rather than letting a partner call /tools/document/*:
those routes authenticate a real user, bill that user's credits, and hold the
connection open for the entire walk. A partner integration has no user here,
does its own billing, and cannot hold a socket open for tens of minutes behind
a proxy. So this module keeps the SAME engine (orchestrator.tools.humanize_docx)
and swaps only the three things that differ: auth, ownership, and an async
contract — start, poll, collect.

No schema migration: state rides on the ToolRun row, which already carries
status / progress_done / progress_total / metrics / output_s3_uri. Runs are
owned by the ensure_partner_user system account with surface="partner", and
every status lookup is scoped to BOTH — a partner token cannot read a real
student's run even by guessing an id.

Honest contract (mirror it in any UI): this reduces the AI-detection "smell" of
the prose. It is NOT a plagiarism/similarity tool and does NOT guarantee
passing any specific detector. Numbers, tables, terms and citations are frozen
— a rewrite that alters one is discarded and the original kept.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import partner_run as prun
from ..db import db_session
from ..models import ToolRun
from ..tool_artifacts import store_run_files, uri_parts
from ..tool_billing import Timer, begin_tool_run, bump_progress, record_tool_run
from .partner_report import _require_partner
from .tools import DocScanOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["partner"])

# How long a row may sit in `running` before status calls it lost. A process
# restart mid-rewrite leaves the row open forever otherwise, and a caller
# polling a dead run learns nothing by polling it for another day. Generous:
# the longest real walk observed is well under an hour.
STALE_AFTER = timedelta(minutes=90)

# Live worker threads, so tests can wait for one deterministically instead of
# sleeping. Production never reads this.
_WORKERS: list[threading.Thread] = []


@router.post("/partner/humanize/scan", response_model=DocScanOut)
async def partner_humanize_scan(
    file: UploadFile = File(...),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> DocScanOut:
    """Report what a rewrite would touch. No LLM, no charge.

    The partner's half of confirm-before-you-spend: the caller prices the job
    from `chars` and shows that price BEFORE anything runs, which it cannot do
    without a free estimate. Recorded anyway (`scan-docx` is in
    pricing.TOOL_FREE) because scan-then-abandon is the drop-off worth watching.
    """
    _require_partner(x_partner_token)

    from orchestrator.tools.humanize_docx import scan_docx  # noqa: PLC0415

    from .tools import _read_docx  # noqa: PLC0415

    body = await _read_docx(file)
    out = scan_docx(body)
    user = prun.ensure_partner_user(db)
    if not out.get("ok"):
        record_tool_run(db, user, surface="partner", tool="scan-docx", ok=False,
                        error=out.get("error") or "unreadable")
        return DocScanOut(ok=False, error=out.get("error"),
                          detail="This file could not be opened as a Word document.")
    record_tool_run(db, user, surface="partner", tool="scan-docx",
                    units=out.get("body_paragraphs") or 0)
    return DocScanOut(**out)


def _join_workers(timeout: float = 60) -> None:
    """TEST HELPER — block until every started walk has finished."""
    for thread in list(_WORKERS):
        thread.join(timeout)


def _presign(uri: str | None, expires: int = 3600) -> str | None:
    """Short-lived GET url for an s3:// artifact uri. None on anything odd."""
    bucket, key = uri_parts(uri or "")
    if not bucket or not key:
        return None
    try:
        from .uploads import s3_from_env  # noqa: PLC0415

        return s3_from_env().generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires)
    except Exception:  # noqa: BLE001
        logger.exception("partner humanize: presign failed for %s", uri)
        return None


def _fail(run_id: int, code: str) -> None:
    """Close a run as failed from the worker. Own session; never raises."""
    from ..db import get_session_factory  # noqa: PLC0415

    try:
        session_factory = get_session_factory()
        with session_factory() as s:
            row = s.get(ToolRun, run_id)
            if row is None:
                return
            row.status, row.ok, row.error = "failed", False, code
            s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("partner humanize: could not mark run %s failed", run_id)


def _walk(run_id: int, user_id, body: bytes, filename: str,
          language: str | None) -> None:
    """The rewrite itself, off the request.

    Never raises. A crash here has to CLOSE the row — a caller polling a run
    that will never answer is worse than a clean failure, and this thread has
    nobody to raise to.
    """
    from orchestrator.tools.humanize_docx import humanize_docx  # noqa: PLC0415

    from ..db import get_session_factory  # noqa: PLC0415
    from ..models import User  # noqa: PLC0415
    from .tools import _humanize_metrics  # noqa: PLC0415

    try:
        with Timer() as timer:
            out, report = humanize_docx(
                body, language=language, user_anchor=None,
                on_progress=lambda done, total: bump_progress(run_id, done=done, total=total))
        ok = out is not None and bool(report.get("ok"))
        # Both halves kept, including on failure: the input is what makes a bad
        # run reproducible without asking the caller for the file again.
        files = store_run_files(user_id=user_id, filename=filename,
                                input_bytes=body, output_bytes=out)
        session_factory = get_session_factory()
        with session_factory() as s:
            user = s.get(User, user_id)
            record_tool_run(
                s, user, surface="partner", tool="humanize-docx", ok=ok,
                error=None if ok else (report.get("error") or "rewrite_failed"),
                usage=report.get("usage") or [], duration_ms=timer.ms,
                run_id=run_id, files=files, input_filename=filename,
                metrics=_humanize_metrics(report))
    except Exception:  # noqa: BLE001
        logger.exception("partner humanize: walk crashed for run %s", run_id)
        _fail(run_id, "rewrite_failed")


def _start_worker(run_id: int, user_id, body: bytes, filename: str,
                  language: str | None) -> None:
    thread = threading.Thread(target=_walk,
                              args=(run_id, user_id, body, filename, language),
                              daemon=True)
    _WORKERS.append(thread)
    thread.start()


class PartnerHumanizeOut(BaseModel):
    run_id: int
    status: str


@router.post("/partner/humanize", response_model=PartnerHumanizeOut)
async def partner_humanize(
    file: UploadFile = File(...),
    # None = read the language off the document. A hard default translates an
    # English thesis instead of re-voicing it (see routers/humanize.py).
    language: str | None = Form(None),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> PartnerHumanizeOut:
    """Start a rewrite and answer immediately with the id to poll.

    Deliberately NOT /partner/report's shape: that route holds one connection
    open for the whole run, and a rewrite is ~70 sequential model calls — any
    proxy in front of either side cuts that long before it finishes.
    """
    _require_partner(x_partner_token)

    from .tools import _read_docx  # noqa: PLC0415

    body = await _read_docx(file)
    user = prun.ensure_partner_user(db)
    db.commit()  # the worker opens its own session and must see this user
    run_id = begin_tool_run(db, user, tool="humanize-docx", surface="partner")
    if not run_id:
        raise HTTPException(503, detail={"error": {
            "code": "run_not_started", "message": "could not open a run row"}})
    filename = file.filename or "document.docx"
    _start_worker(run_id, user.id, body, filename, language)
    return PartnerHumanizeOut(run_id=run_id, status="processing")


class PartnerHumanizeStatusIn(BaseModel):
    run_id: int


@router.post("/partner/humanize/status")
def partner_humanize_status(
    body: PartnerHumanizeStatusIn,
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> dict:
    """Poll one partner run.

    Scoped to the partner system user AND surface="partner": ids are sequential
    and partner auth is one shared secret, so without that scope a guessed id
    would read a real student's run.
    """
    _require_partner(x_partner_token)
    user = prun.ensure_partner_user(db)
    row = db.scalar(
        select(ToolRun).where(ToolRun.id == body.run_id,
                              ToolRun.user_id == user.id,
                              ToolRun.surface == "partner",
                              ToolRun.tool == "humanize-docx"))
    if row is None:
        raise HTTPException(404, detail={"error": {
            "code": "not_found", "message": "no such partner run"}})

    common = {"done": row.progress_done, "total": row.progress_total,
              "filename": row.input_filename,
              "credits_charged": row.credits_charged,
              "metrics": row.metrics}
    if row.status == "running":
        created = row.created_at
        if created and datetime.now(timezone.utc) - created > STALE_AFTER:
            return {**common, "status": "error", "ok": False,
                    "error": "run_lost", "docx_url": None}
        return {**common, "status": "processing", "ok": False,
                "error": None, "docx_url": None}
    if not row.ok:
        return {**common, "status": "error", "ok": False,
                "error": row.error or "rewrite_failed", "docx_url": None}
    return {**common, "status": "done", "ok": True, "error": None,
            "docx_url": _presign(row.output_s3_uri)}

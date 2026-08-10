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

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import partner_run as prun
from ..db import db_session
from ..tool_artifacts import store_run_files
from ..tool_billing import Timer, begin_tool_run, bump_progress, record_tool_run
from .partner_docx import (
    fail_run, find_partner_run, join_workers, start_worker, status_payload)
from .partner_report import _require_partner
from .tools import DocScanOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["partner"])

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
        fail_run(run_id, "rewrite_failed")


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
    start_worker(_walk, run_id, user.id, body, filename, language)
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
    row = find_partner_run(db, body.run_id, user.id, "humanize-docx")
    if row is None:
        raise HTTPException(404, detail={"error": {
            "code": "not_found", "message": "no such partner run"}})
    payload = status_payload(row)
    # This tool's failures are rewrites that produced nothing, so an unlabelled
    # failure reads as rewrite_failed rather than the generic default.
    if payload["status"] == "error" and payload["error"] == "failed":
        payload["error"] = "rewrite_failed"
    return payload

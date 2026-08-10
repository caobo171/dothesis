"""Partner citation generation — resolve and add citations in a .docx, behind
the shared partner secret.

Async like partner_humanize and for the same reason: phase A is a CrossRef
round trip per source and phase B is a model call per uncited claim, so a real
thesis blocks for minutes. Start, poll, collect.

WHAT A PARTNER MUST TELL THE USER
---------------------------------
`unresolved` and `marked` are not incidental counters. The tool is built to fail
closed — the model never supplies a reference, only a search query and a yes/no
on what CrossRef returned — so a claim it cannot source is left with a visible
"[cần nguồn]" marker instead of an invented citation. That is the feature
working, not failing, and a UI that hides those counts turns "we could not find
a source for 12 claims" into silence the student discovers at their defence.
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
from .partner_docx import fail_run, find_partner_run, start_worker, status_payload
from .partner_report import _require_partner

logger = logging.getLogger(__name__)
router = APIRouter(tags=["partner"])


class PartnerCiteScanOut(BaseModel):
    ok: bool
    intext_citations: int = 0
    distinct_sources: int = 0
    existing_references: int = 0
    has_reference_section: bool = False
    body_paragraphs: int = 0
    passages: int = 0
    error: str | None = None
    detail: str | None = None


@router.post("/partner/citation/scan", response_model=PartnerCiteScanOut)
async def partner_citation_scan(
    file: UploadFile = File(...),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> PartnerCiteScanOut:
    """What citing would touch. No CrossRef, no model, no charge.

    `distinct_sources` is the number a partner prices phase A on, and
    `has_reference_section` is what tells a student whether their document is
    even shaped like something this can work with.
    """
    _require_partner(x_partner_token)

    from orchestrator.tools.cite_docx import scan_cite_docx  # noqa: PLC0415

    from .tools import _read_docx  # noqa: PLC0415

    body = await _read_docx(file)
    out = scan_cite_docx(body)
    user = prun.ensure_partner_user(db)
    if not out.get("ok"):
        record_tool_run(db, user, surface="partner", tool="scan-cite-docx",
                        ok=False, error=out.get("error") or "unreadable")
        return PartnerCiteScanOut(
            ok=False, error=out.get("error"),
            detail="This file could not be opened as a Word document.")
    record_tool_run(db, user, surface="partner", tool="scan-cite-docx",
                    units=out.get("distinct_sources") or 0)
    # Drop keys the partner contract does not carry (headings/tables), so
    # adding one upstream cannot break this response model.
    keep = PartnerCiteScanOut.model_fields.keys()
    return PartnerCiteScanOut(**{k: v for k, v in out.items() if k in keep})


def _walk(run_id: int, user_id, body: bytes, filename: str, add_missing: bool) -> None:
    """Resolve and cite, off the request. Never raises — a crash has to close
    the row rather than strand a caller polling a run that will never answer."""
    from orchestrator.tools.cite_docx import cite_docx  # noqa: PLC0415

    from ..db import get_session_factory  # noqa: PLC0415
    from ..models import User  # noqa: PLC0415

    try:
        with Timer() as timer:
            out, report = cite_docx(
                body, add_missing=add_missing,
                on_progress=lambda done, total: bump_progress(run_id, done=done, total=total))
        ok = out is not None and bool(report.get("ok"))
        files = store_run_files(user_id=user_id, filename=filename,
                                input_bytes=body, output_bytes=out)
        # Billed per source ACTUALLY looked up — resolved plus unresolved, since
        # a CrossRef query was spent either way — plus phase B's tokens.
        sources = int(report.get("resolved") or 0) + int(report.get("unresolved") or 0)
        session_factory = get_session_factory()
        with session_factory() as s:
            user = s.get(User, user_id)
            record_tool_run(
                s, user, surface="partner", tool="cite-docx", ok=ok,
                error=None if ok else (report.get("error") or "cite_failed"),
                units=sources, usage=report.get("usage") or [],
                duration_ms=timer.ms, run_id=run_id, files=files,
                input_filename=filename,
                metrics={k: report.get(k, 0) for k in (
                    "resolved", "unresolved", "weak", "orphans", "added",
                    "marked", "linked", "references")})
    except Exception:  # noqa: BLE001
        logger.exception("partner citation: run crashed for run %s", run_id)
        fail_run(run_id, "cite_failed")


class PartnerCiteOut(BaseModel):
    run_id: int
    status: str


@router.post("/partner/citation", response_model=PartnerCiteOut)
async def partner_citation(
    file: UploadFile = File(...),
    # False runs phase A only — resolve what is already cited and rebuild the
    # reference list. No model, so it is the half that cannot go wrong, and a
    # partner may want to sell it separately.
    add_missing: bool = Form(True),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> PartnerCiteOut:
    """Start a citation run and answer immediately with the id to poll."""
    _require_partner(x_partner_token)

    from .tools import _read_docx  # noqa: PLC0415

    body = await _read_docx(file)
    user = prun.ensure_partner_user(db)
    db.commit()  # the worker opens its own session and must see this user
    run_id = begin_tool_run(db, user, tool="cite-docx", surface="partner")
    if not run_id:
        raise HTTPException(503, detail={"error": {
            "code": "run_not_started", "message": "could not open a run row"}})
    start_worker(_walk, run_id, user.id, body,
                 file.filename or "document.docx", bool(add_missing))
    return PartnerCiteOut(run_id=run_id, status="processing")


class PartnerCiteStatusIn(BaseModel):
    run_id: int


@router.post("/partner/citation/status")
def partner_citation_status(
    body: PartnerCiteStatusIn,
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> dict:
    """Poll one citation run. Scoped to the partner system user and surface."""
    _require_partner(x_partner_token)
    user = prun.ensure_partner_user(db)
    row = find_partner_run(db, body.run_id, user.id, "cite-docx")
    if row is None:
        raise HTTPException(404, detail={"error": {
            "code": "not_found", "message": "no such partner run"}})
    payload = status_payload(row)
    if payload["status"] == "error" and payload["error"] == "failed":
        payload["error"] = "cite_failed"
    return payload

"""Partner similarity & citation self-check — the .docx checker, reachable with
the shared partner secret instead of a student's session.

Sibling of partner_humanize.py, and deliberately a SIMPLER shape: the humanize
walk is ~70 sequential model calls and needs a start/poll/collect contract,
while this one is a shingle index over the document plus (when configured) one
vendor round trip — seconds, not tens of minutes. So it answers in a single
request, and the caller gets the annotated file's key straight back.

WHAT A PARTNER MUST NOT DO WITH THIS
------------------------------------
`corpus_checked: false` means NOBODY LOOKED at the web or any paper index. It
does NOT mean the document is clean, and a partner UI that renders it as a pass
is lying to a student about the one thing they came to find out. The field is
returned on every response, including failures, so there is no path where a
caller can forget to ask. See orchestrator/tools/similarity_docx.py's docstring
for what the offline half actually covers — internal duplication and quote
hygiene, which is what usually drives a similarity score in the first place.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import partner_run as prun
from ..db import db_session
from ..tool_artifacts import store_run_files
from ..tool_billing import Timer, record_tool_run
from .partner_docx import presign
from .partner_report import _require_partner

logger = logging.getLogger(__name__)
router = APIRouter(tags=["partner"])


class PartnerSimScanOut(BaseModel):
    ok: bool
    paragraphs: int = 0
    body_paragraphs: int = 0
    words: int = 0
    quotations: int = 0
    in_text_citations: int = 0
    reference_entries: int = 0
    # False = no external index will be searched. The partner prices and words
    # its UI off this, so it ships with the QUOTE, not just with the result.
    corpus_available: bool = False
    error: str | None = None
    detail: str | None = None


@router.post("/partner/similarity/scan", response_model=PartnerSimScanOut)
async def partner_similarity_scan(
    file: UploadFile = File(...),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> PartnerSimScanOut:
    """What the check would look at, and whether a corpus is even available.
    No model, no vendor, no charge."""
    _require_partner(x_partner_token)

    from orchestrator.tools.plagiarism import get_provider  # noqa: PLC0415
    from orchestrator.tools.similarity_docx import scan_docx  # noqa: PLC0415

    from .tools import _read_docx  # noqa: PLC0415

    body = await _read_docx(file)
    out = scan_docx(body)
    user = prun.ensure_partner_user(db)
    if not out.get("ok"):
        record_tool_run(db, user, surface="partner", tool="scan-similarity-docx",
                        ok=False, error=out.get("error") or "unreadable")
        return PartnerSimScanOut(
            ok=False, error=out.get("error"),
            detail="This file could not be opened as a Word document.")
    record_tool_run(db, user, surface="partner", tool="scan-similarity-docx",
                    units=out.get("body_paragraphs") or 0)
    return PartnerSimScanOut(**out, corpus_available=get_provider() is not None)


class PartnerSimOut(BaseModel):
    ok: bool
    # Load-bearing: false = nobody searched an external index. Never render it
    # as "no plagiarism found".
    corpus_checked: bool = False
    corpus_error: str | None = None
    # Per-finding counts: flagged_paragraphs, internal_duplication,
    # uncited_quotations, cited_not_in_references, references_never_cited.
    counts: dict = {}
    # Presigned URL for the annotated .docx, plus its s3:// uri so a partner
    # that keeps its own copy can fetch and re-store it.
    docx_url: str | None = None
    docx_uri: str | None = None
    credits_charged: int = 0
    error: str | None = None


@router.post("/partner/similarity", response_model=PartnerSimOut)
async def partner_similarity(
    file: UploadFile = File(...),
    language: str = Form("vi"),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
    db: Session = Depends(db_session),
) -> PartnerSimOut:
    """Run the check and answer in one request.

    Off the event loop like the web route: the shingle index over a
    300-paragraph thesis is CPU-bound for seconds, and a configured provider
    adds a network round trip on top — enough to block everything else if it
    ran inline.
    """
    _require_partner(x_partner_token)

    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

    from orchestrator.tools.plagiarism import get_provider  # noqa: PLC0415
    from orchestrator.tools.similarity_docx import similarity_docx  # noqa: PLC0415

    from .tools import _read_docx  # noqa: PLC0415

    body = await _read_docx(file)
    provider = get_provider()
    user = prun.ensure_partner_user(db)

    with Timer() as timer:
        out, report = await run_in_threadpool(
            similarity_docx, body, provider=provider, language=language)
    ok = out is not None and bool(report.get("ok"))

    files = await run_in_threadpool(
        store_run_files, user_id=user.id,
        filename=file.filename or "document.docx",
        input_bytes=body, output_bytes=out)

    # The corpus surcharge is charged only when a provider actually RAN — a
    # configured-but-unreachable vendor bills the offline half and no more.
    tool = "similarity-docx-corpus" if report.get("corpus_checked") else "similarity-docx"
    charged = record_tool_run(
        db, user, surface="partner", tool=tool, ok=ok,
        error=None if ok else (report.get("error") or "similarity_failed"),
        duration_ms=timer.ms, files=files,
        input_filename=file.filename, metrics=report.get("counts") or {}).charged

    if not ok:
        raise HTTPException(422, detail={"error": {
            "code": report.get("error") or "similarity_failed",
            "message": "This file could not be checked."}})

    return PartnerSimOut(
        ok=True,
        corpus_checked=bool(report.get("corpus_checked")),
        corpus_error=report.get("corpus_error"),
        counts=report.get("counts") or {},
        docx_url=presign(files.output_uri),
        docx_uri=files.output_uri,
        credits_charged=charged,
    )

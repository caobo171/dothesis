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

from fastapi import APIRouter, Depends, File, Header, UploadFile
from sqlalchemy.orm import Session

from .. import partner_run as prun
from ..db import db_session
from ..tool_billing import record_tool_run
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

"""Partner report endpoint — service-to-service ("Powered by DoThesis").

A trusted partner app (e.g. Fillform) POSTs a statistical-analysis PDF plus a
`depth`, authenticates with a shared token in the `X-Partner-Token` header, and
gets back short-lived DOCX/PDF download URLs. This path is deliberately NOT the
user chat/credit flow: no JWT, no project, no credit ledger — the partner owns
the end-user relationship and any billing.

Auth is a single shared secret (settings.partner_api_token). Empty secret ->
the endpoint 401s on every call, so it stays closed until explicitly enabled.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..partner_report_service import ReportError, generate_partner_report, get_progress
from ..settings import get_settings

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
    powered_by: str = "DoThesis"


@router.post("/partner/report", response_model=PartnerReportOut)
async def create_partner_report(
    file: UploadFile = File(...),
    depth: str = Form("analysis_report"),
    # Optional comma-separated subset of intro,lit_review,methodology,results,
    # discussion,conclusion. When set it overrides `depth` (the "tick Chương N"
    # path). Empty/absent falls back to `depth`.
    chapters: str | None = Form(None),
    # Opaque token the partner also passes to /partner/report/progress to poll
    # live per-chapter progress while this (long) call is still running.
    progress_token: str | None = Form(None),
    title: str | None = Form(None),
    # Optional free-text context the end user typed to steer the writing.
    notes: str | None = Form(None),
    language: str = Form("en"),
    # Optional caller-supplied M1/M2/M3 modules as JSON strings (the input
    # contract). Each present one is used verbatim by the service; missing ones
    # are generated. Sent as form fields so they ride alongside the file upload.
    m1: str | None = Form(None),
    m2: str | None = Form(None),
    m3: str | None = Form(None),
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
):
    _require_partner(x_partner_token)

    if file.content_type and file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            415,
            detail={"error": {"code": "unsupported_media_type",
                              "message": f"expected a PDF, got {file.content_type}"}},
        )

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(422, detail={"error": {"code": "empty_file", "message": "no file bytes"}})
    if len(pdf_bytes) > _MAX_BYTES:
        raise HTTPException(
            413,
            detail={"error": {"code": "file_too_large",
                              "message": f"max {_MAX_BYTES // (1024 * 1024)}MB"}},
        )

    chapter_list = [c.strip() for c in chapters.split(",") if c.strip()] if chapters else None

    # Parse each optional module JSON up front so a malformed shape is a clean
    # 422 (never a silent drop / silent overwrite of a caller-provided module).
    import json

    def _parse(name, raw):
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
    m1_d, m2_d, m3_d = _parse("m1", m1), _parse("m2", m2), _parse("m3", m3)

    try:
        # Blocking (pdfminer + LLM compose + LibreOffice render) — off the loop.
        result = await run_in_threadpool(
            generate_partner_report,
            pdf_bytes,
            depth=depth,
            chapters=chapter_list,
            progress_token=progress_token,
            filename=file.filename,
            title=title,
            notes=notes,
            language=language,
            m1=m1_d,
            m2=m2_d,
            m3=m3_d,
        )
    except ReportError as e:
        # bad_depth / bad_chapters / no_extractable_text -> 422; compose_failed -> 502.
        status = 502 if e.code == "compose_failed" else 422
        raise HTTPException(status, detail={"error": {"code": e.code, "message": e.message}})
    except Exception:
        logger.exception("partner_report: unexpected failure")
        raise HTTPException(
            500, detail={"error": {"code": "report_failed", "message": "report generation failed"}},
        )

    # F5: partner surface export completed. Headless (no user id) — pass None;
    # best-effort so the partner path gains no blocking logic (headless invariant).
    from ..analytics import emit
    emit("export_completed", None,
         {"scope": ",".join(chapter_list) if chapter_list else depth, "surface": "partner"})
    return result


class ProgressIn(BaseModel):
    progress_token: str


class ProgressOut(BaseModel):
    status: str  # processing | done | error | unknown
    phase: str | None = None       # extract | compose | export | done
    total: int | None = None
    done: int | None = None
    current: str | None = None     # title of the chapter being composed


@router.post("/partner/report/progress", response_model=ProgressOut)
async def partner_report_progress(
    body: ProgressIn,
    x_partner_token: str | None = Header(None, alias="X-Partner-Token"),
):
    """Poll live per-chapter progress for an in-flight report (by progress_token)."""
    _require_partner(x_partner_token)
    p = get_progress(body.progress_token)
    if not p:
        return {"status": "unknown"}
    return {
        "status": p.get("status", "processing"),
        "phase": p.get("phase"),
        "total": p.get("total"),
        "done": p.get("done"),
        "current": p.get("current"),
    }

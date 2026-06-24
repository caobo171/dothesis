"""SP6: download endpoint for M5 export artifacts.

Mounted under /api/v1 by app/main.py only when ORCHESTRATOR_ENABLED=true.
Resolves the s3_key from the project's M5Output.export_artifacts and
302-redirects the browser to a fresh 5-minute signed URL.
"""
from __future__ import annotations

import io
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agent_state import DbProjectStateStore
from ..db import db_session
from ..deps import current_user, stream_user_factory
from ..models import ContextStore, Project, User
from ..routers.uploads import s3_from_env

router = APIRouter(tags=["exports"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Modules that can be exported on their own as a teacher-report Word doc. M5 is
# excluded — it already has the full-thesis docx/pdf export.
_MODULE_EXPORT = {
    "M1": ("m1_topic", "Topic Discovery"),
    "M2": ("m2_literature", "Literature Review"),
    "M3": ("m3_design", "Research Design"),
    "M4": ("m4_analysis", "Data Analysis"),
}


def _humanize(key: str) -> str:
    return key.replace("_", " ").strip().title()


def _slug(name: str | None) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "thesis").lower()).strip("-")
    return s or "thesis"


def _stringify(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return "; ".join(_stringify(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{_humanize(k)}: {_stringify(val)}" for k, val in v.items())
    return str(v)


_SKIP_KEYS = {"confirmed_at", "needs_review", "module_status", "focus"}
_LIKERT_TYPES = {"scale", "likert"}


def _authors_str(src: dict) -> str:
    a = src.get("authors") or src.get("author")
    if isinstance(a, list):
        return ", ".join(str(x) for x in a)
    return str(a) if a else "Anon"


def _citation_line(src: dict) -> str:
    """A clean reference line: Authors (Year). Title. Venue."""
    yr = src.get("year") or "n.d."
    parts = [f"{_authors_str(src)} ({yr})."]
    if src.get("title"):
        parts.append(f"{str(src['title']).rstrip('.')}.")
    if src.get("venue") or src.get("journal"):
        parts.append(f"{src.get('venue') or src.get('journal')}.")
    return " ".join(parts)


def _render_obj(doc, obj: Any) -> None:
    """Render a free-shaped value as readable prose/bullets (for model/methodology)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _SKIP_KEYS or str(k).startswith("_"):
                continue
            p = doc.add_paragraph()
            p.add_run(f"{_humanize(k)}: ").bold = True
            p.add_run(_stringify(v))
    elif isinstance(obj, list):
        for it in obj:
            doc.add_paragraph(_stringify(it), style="List Bullet")
    elif obj not in (None, ""):
        for line in str(obj).split("\n"):
            doc.add_paragraph(line)


def _render_m1(doc, s: dict) -> None:
    if s.get("research_title"):
        doc.add_heading("Research Title", level=1)
        doc.add_paragraph(str(s["research_title"]))
    rqs = s.get("research_questions") or []
    if rqs:
        doc.add_heading("Research Questions", level=1)
        for i, q in enumerate(rqs):
            p = doc.add_paragraph(style="List Number")
            p.add_run(("Main — " if i == 0 else "") + str(q))


def _render_m2(doc, s: dict) -> None:
    sources = s.get("literature_sources") or []
    if sources:
        doc.add_heading("Reviewed Literature", level=1)
        doc.add_paragraph(f"{len(sources)} verified academic sources.")
        for src in sources:
            p = doc.add_paragraph(style="List Number")
            p.add_run(_citation_line(src))
            if src.get("doi"):
                p.add_run(f"  https://doi.org/{src['doi']}").italic = True
    gaps = s.get("research_gaps") or []
    if gaps:
        doc.add_heading("Identified Research Gaps", level=1)
        for g in gaps:
            if isinstance(g, dict):
                doc.add_heading(str(g.get("title", "Gap")), level=2)
                if g.get("description"):
                    doc.add_paragraph(str(g["description"]))
            else:
                doc.add_paragraph(str(g), style="List Bullet")


def _render_m3(doc, s: dict) -> None:
    if s.get("conceptual_model"):
        doc.add_heading("Conceptual Model", level=1)
        _render_obj(doc, s["conceptual_model"])
    hyps = s.get("hypotheses") or []
    if hyps:
        doc.add_heading("Hypotheses", level=1)
        for h in hyps:
            doc.add_paragraph(str(h), style="List Bullet")
    if s.get("methodology"):
        doc.add_heading("Methodology", level=1)
        _render_obj(doc, s["methodology"])
    inst = s.get("instrument")
    if inst:
        title = inst.get("title") if isinstance(inst, dict) else None
        doc.add_heading(f"Instrument — {title}" if title else "Instrument", level=1)
        questions = inst.get("questions") if isinstance(inst, dict) else None
        if questions:
            for q in questions:
                p = doc.add_paragraph(style="List Number")
                p.add_run(str(q.get("text", ""))).bold = True
                if q.get("required"):
                    p.add_run("  (required)").italic = True
                qtype = str(q.get("type", "")).lower()
                opts = q.get("options") or []
                if qtype in _LIKERT_TYPES:
                    lo, hi = q.get("scale_min", 1), q.get("scale_max", 5)
                    lab = ""
                    if q.get("scale_min_label") or q.get("scale_max_label"):
                        lab = f" ({q.get('scale_min_label','')} → {q.get('scale_max_label','')})"
                    doc.add_paragraph(f"{lo}–{hi} Likert scale{lab}").italic = True
                else:
                    for o in opts:
                        doc.add_paragraph(f"☐ {o}")
        else:
            _render_obj(doc, inst)


def _render_m4(doc, s: dict) -> None:
    if s.get("analysis_outline"):
        doc.add_heading("Analysis Plan", level=1)
        _render_obj(doc, s["analysis_outline"])
    if s.get("analysis_results"):
        doc.add_heading("Results", level=1)
        _render_obj(doc, s["analysis_results"])


_MODULE_RENDERERS = {"M1": _render_m1, "M2": _render_m2, "M3": _render_m3, "M4": _render_m4}


def _build_module_docx(project_name: str, module: str, label: str, slice_: dict) -> io.BytesIO:
    """Render one module's context_store slice into a teacher-ready academic report
    (titled, sectioned prose — like M5's thesis export, but a single-module summary)."""
    from docx import Document  # local import: keeps cold-start light

    doc = Document()
    # Cover: research title (falls back to project name) + module subtitle.
    doc.add_heading(str(slice_.get("research_title") or project_name or "Untitled thesis"), level=0)
    sub = doc.add_paragraph()
    sub.add_run(f"{module} — {label}").bold = True
    note = doc.add_paragraph()
    note.add_run("Module report · generated by DoThesis").italic = True

    if not slice_:
        doc.add_paragraph("No content has been produced for this module yet.")
    else:
        renderer = _MODULE_RENDERERS.get(module)
        if renderer:
            renderer(doc, slice_)
        else:  # graceful fallback for any unexpected module
            for key, value in slice_.items():
                if key in _SKIP_KEYS or str(key).startswith("_"):
                    continue
                doc.add_heading(_humanize(key), level=1)
                _render_obj(doc, value)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


class ModuleExportBody(BaseModel):
    module: str
    # Declared so the JSON body validates; the value is consumed by current_user.
    access_token: str | None = None


@router.post("/projects/{project_id}/export/module")
def export_module_docx(
    project_id: uuid.UUID,
    body: ModuleExportBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Stream a single module (M1–M4) as a Word doc for a teacher report.

    Built on the fly from the project's context_store slice and returned
    directly (no S3) so it works regardless of object-storage config.
    """
    proj = _owned_project(db, user, project_id)
    module = body.module.upper()
    if module not in _MODULE_EXPORT:
        raise HTTPException(400, detail={"error": {"code": "bad_module",
                                                   "message": f"exportable: {list(_MODULE_EXPORT)}"}})
    column, label = _MODULE_EXPORT[module]
    store = DbProjectStateStore(db.bind, project_id, Path(tempfile.gettempdir()))
    slice_ = (store.load_full_context_store().get(column)) or {}
    buf = _build_module_docx(proj.name or "Untitled thesis", module, label, slice_)
    filename = f"{_slug(proj.name)}-{module.lower()}-{column}.docx"
    return StreamingResponse(
        buf, media_type=_DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    # Raise 404 (not 403) to avoid leaking project existence to non-owners.
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found"}},
        )
    return p


@router.get("/projects/{project_id}/exports/{filename}")
def download_export(
    project_id: uuid.UUID, filename: str,
    # GET-only (browser <a download>). Auth via a short-lived ?st= token scoped
    # to exactly this artifact, keeping the long-lived JWT out of the URL/logs.
    user: User = Depends(stream_user_factory(
        lambda project_id, filename: f"project-export:{project_id}/{filename}")),
    db: Session = Depends(db_session),
):
    """302-redirect to a fresh 5-minute signed URL for the requested artifact."""
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    m5 = (cs.m5_writing or {}) if cs else {}
    artifacts = m5.get("export_artifacts") or []
    expected_key = f"projects/{project_id}/exports/{filename}"
    # Only redirect if the artifact key is present — prevents guessing other keys.
    if not any(a.get("s3_key") == expected_key for a in artifacts):
        raise HTTPException(
            404, detail={"error": {"code": "artifact_not_found"}},
        )
    s3 = s3_from_env()
    signed_url = s3.generate_presigned_url(
        "get_object",
        # Project convention is S3_BUCKET; AWS_S3_BUCKET kept as a fallback.
        Params={"Bucket": os.environ.get("S3_BUCKET") or os.environ["AWS_S3_BUCKET"],
                "Key": expected_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url=signed_url, status_code=302)

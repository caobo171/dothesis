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


def _render_value(doc, value: Any) -> None:
    if value in (None, "", [], {}):
        doc.add_paragraph("—")
        return
    if isinstance(value, str):
        for line in value.split("\n"):
            doc.add_paragraph(line)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                # Prefer human-meaningful fields (citations, hypotheses, etc.).
                parts = [str(item[k]) for k in
                         ("title", "author", "authors", "year", "venue", "name",
                          "statement", "text", "doi")
                         if item.get(k)]
                doc.add_paragraph(" · ".join(parts) if parts else _stringify(item),
                                  style="List Bullet")
            else:
                doc.add_paragraph(str(item), style="List Bullet")
    elif isinstance(value, dict):
        for k, v in value.items():
            p = doc.add_paragraph()
            run = p.add_run(f"{_humanize(k)}: ")
            run.bold = True
            p.add_run(_stringify(v))
    else:
        doc.add_paragraph(str(value))


def _build_module_docx(project_name: str, module: str, label: str, slice_: dict) -> io.BytesIO:
    """Render one module's context_store slice into a simple, teacher-ready .docx."""
    from docx import Document  # local import: keeps cold-start light

    doc = Document()
    doc.add_heading(f"{project_name}", level=0)
    doc.add_heading(f"{module} — {label}", level=1)
    if not slice_:
        doc.add_paragraph("No content has been produced for this module yet.")
    else:
        for key, value in slice_.items():
            if key.startswith("_") or key.endswith("_status"):
                continue  # skip internal/bookkeeping keys
            doc.add_heading(_humanize(key), level=2)
            _render_value(doc, value)

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

"""SP6.5: editor API — chapter prose CRUD, inline AI tools, accept/reject."""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..db import db_session
from ..deps import current_user
from ..models import ContextStore, Project, User

router = APIRouter(tags=["m5_editor"])


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    """Reuse the SP6 exports.py pattern: 404 (not 403) to avoid existence leaks."""
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found"}})
    return p


def _m5_slice(db: Session, project_id: uuid.UUID) -> dict:
    """Return the m5_writing JSONB blob, or {} if not yet seeded."""
    cs = db.get(ContextStore, project_id)
    return (cs.m5_writing or {}) if cs else {}


@router.get("/projects/{project_id}/m5/chapters")
def list_chapters(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Return all chapters from m5_writing.chapters, or {} if none exist yet."""
    _owned_project(db, user, project_id)
    m5 = _m5_slice(db, project_id)
    return m5.get("chapters", {})


# ---------------------------------------------------------------------------
# PATCH /projects/{project_id}/m5/chapters/{chapter_name} — autosave
# ---------------------------------------------------------------------------

_VALID_CHAPTER_NAMES = {
    "intro", "lit_review", "methodology", "results", "discussion", "conclusion"
}


class PatchChapterBody(BaseModel):
    prose: str


def _collect_reference_pool(cs: ContextStore) -> list[dict]:
    """Mirror M5Agent._collect_references: dedupe by (author, year) preserving order.

    Decision: centralised here so the PATCH endpoint and the agent share identical
    pool-building logic without duplicating it or importing from the agent layer.
    """
    m2 = (cs.m2_literature or {}) if cs else {}
    seen: dict[tuple, dict] = {}
    for gap in m2.get("research_gaps", []) or []:
        for paper in (gap.get("supporting_papers") or []):
            key = (str(paper.get("author", "")), str(paper.get("year", "")))
            if key not in seen:
                seen[key] = paper
    return list(seen.values())


@router.patch("/projects/{project_id}/m5/chapters/{chapter_name}")
def patch_chapter(
    project_id: uuid.UUID,
    chapter_name: str,
    body: PatchChapterBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Autosave prose for a single chapter and revalidate its inline citations.

    Decision: 404 on unknown/undrafted chapter names (rather than 400) so the
    client cannot probe which chapters exist on projects it doesn't own.
    """
    # Reject chapter names that are outside the allowed set before touching the DB
    if chapter_name not in _VALID_CHAPTER_NAMES:
        raise HTTPException(404, detail={"error": {"code": "unknown_chapter"}})
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    if cs is None:
        raise HTTPException(404, detail={"error": {"code": "no_context"}})
    m5 = cs.m5_writing or {}
    chapters = m5.get("chapters") or {}
    if chapter_name not in chapters:
        raise HTTPException(404, detail={"error": {"code": "chapter_not_drafted"}})

    # Re-validate citations so the front-end always has fresh used/uncited lists
    from orchestrator.tools.m5_writing import validate_citations_plain
    pool = _collect_reference_pool(cs)
    validation = validate_citations_plain(body.prose, pool)

    chapters[chapter_name]["prose"] = body.prose
    chapters[chapter_name]["citations_used"] = validation["citations_used"]
    chapters[chapter_name]["uncited_warnings"] = validation["uncited_warnings"]
    m5["chapters"] = chapters
    cs.m5_writing = m5
    # Decision: flag_modified is required for SQLAlchemy to detect mutations of
    # JSONB columns assigned via dict (not detected by Python identity checks).
    flag_modified(cs, "m5_writing")
    db.commit()
    return chapters[chapter_name]


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/m5/references — M2 reference pool with stable ids
# ---------------------------------------------------------------------------


def _reference_id(ref: dict) -> str:
    """Stable derived id: sha1(author + year). Keeps the wire shape stable
    across server restarts without forcing a DB schema for references.

    Decision: Truncate to 16 hex chars for brevity while maintaining collision
    resistance for practical reference pool sizes. The cite endpoint (Task 13)
    uses the same function to map ref_id back to the paper.
    """
    raw = f"{ref.get('author', '')}|{ref.get('year', '')}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


@router.get("/projects/{project_id}/m5/references")
def list_references(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Return the M2 reference pool (deduplicated) with stable hash ids.

    Decision: Returns [] if no M2 literature exists. Each reference in the
    response includes all fields from the original paper (author, year, title, etc.)
    plus a computed "id" field for stable identification across restarts.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    pool = _collect_reference_pool(cs) if cs else []
    return [{"id": _reference_id(r), **r} for r in pool]

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


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/m5/chapters/{chapter_name}/paraphrase
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402 — stdlib, safe to re-import
from uuid import uuid4  # noqa: E402

from orchestrator.schemas.m5_editor import PendingEdit  # noqa: E402
from orchestrator.tools.m5_inline import paraphrase_selection, translate_selection, build_citation_text  # noqa: E402 — translate_selection + build_citation_text reused by Tasks 12+13


class ParaphraseBody(BaseModel):
    from_offset: int
    to_offset: int
    style: str = ""


def _validate_range(prose: str, from_offset: int, to_offset: int) -> None:
    """Raise 400 when the selection window is outside the current prose length.

    Decision: guard fires before any LLM call to avoid paying API cost on
    invalid input. from_offset == to_offset is allowed (insertion point).
    """
    if from_offset < 0 or to_offset < from_offset or to_offset > len(prose):
        raise HTTPException(400, detail={"error": {"code": "offset_out_of_range"}})


def _surrounding_context(prose: str, from_offset: int, to_offset: int) -> tuple[str, str]:
    """~200 chars before and after the selection for LLM context.

    Decision: truncate rather than fail — the LLM degrades gracefully on
    shorter context whereas an error here blocks the whole feature.
    """
    before = prose[max(0, from_offset - 200): from_offset]
    after = prose[to_offset: to_offset + 200]
    return before, after


def _append_pending_edit(cs: ContextStore, chapter_name: str, pe: PendingEdit) -> dict:
    """Mutate cs.m5_writing in-place and mark the column dirty for SQLAlchemy.

    Decision: flag_modified is required because SQLAlchemy cannot detect
    mutations inside a nested dict assigned to a JSONB column by identity.
    Returns the serialised edit dict so callers can return it directly.
    """
    m5 = cs.m5_writing or {}
    chapters = m5.get("chapters") or {}
    ch = chapters[chapter_name]
    existing = ch.get("pending_edits") or []
    edit_dict = pe.model_dump(mode="json")
    ch["pending_edits"] = existing + [edit_dict]
    chapters[chapter_name] = ch
    m5["chapters"] = chapters
    cs.m5_writing = m5
    flag_modified(cs, "m5_writing")
    return edit_dict


def _load_chapter_or_404(cs: ContextStore, chapter_name: str) -> dict:
    """Return the chapter dict or raise 404.

    Decision: unknown chapter names (not in the allowed set) and undrafted
    chapters (valid name but not yet written) both return 404 for the same
    reason as PATCH — the caller must not be able to probe chapter existence
    on projects they don't own.
    """
    if chapter_name not in _VALID_CHAPTER_NAMES:
        raise HTTPException(404, detail={"error": {"code": "unknown_chapter"}})
    chapters = ((cs.m5_writing or {}).get("chapters") or {}) if cs else {}
    if chapter_name not in chapters:
        raise HTTPException(404, detail={"error": {"code": "chapter_not_drafted"}})
    return chapters[chapter_name]


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/paraphrase")
def paraphrase_chapter_selection(
    project_id: uuid.UUID,
    chapter_name: str,
    body: ParaphraseBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Paraphrase a text selection in a chapter and return a PendingEdit.

    Decision: The endpoint creates a PendingEdit (not an accepted edit) so the
    front-end can present an accept/reject ribbon before the prose is mutated.
    The LLM receives ±200 chars of surrounding context to produce a paraphrase
    that fits naturally into the surrounding prose.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    _validate_range(prose, body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    language = ((cs.m1_topic or {}).get("language", "en")) if cs else "en"
    new_text = paraphrase_selection.invoke({
        "chapter_name": chapter_name,
        "language": language,
        "context_before": before,
        "selection": selection,
        "context_after": after,
        "style": body.style,
    })
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.from_offset,
        to_offset=body.to_offset,
        old_text=selection,
        new_text=new_text,
        source="paraphrase",
        pending_at=datetime.now(timezone.utc),
        metadata={"style": body.style} if body.style else {},
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/m5/chapters/{chapter_name}/translate
# ---------------------------------------------------------------------------


class TranslateBody(BaseModel):
    from_offset: int
    to_offset: int
    target_lang: str


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/translate")
def translate_chapter_selection(
    project_id: uuid.UUID,
    chapter_name: str,
    body: TranslateBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Translate a text selection in a chapter and return a PendingEdit.

    Decision: Mirrors the paraphrase endpoint — creates a PendingEdit so the
    front-end can present an accept/reject ribbon before the prose is mutated.
    The LLM receives target_lang + ±200 chars of surrounding context to produce
    a translation that fits naturally into the surrounding prose.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    _validate_range(prose, body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    new_text = translate_selection.invoke({
        "chapter_name": chapter_name,
        "target_lang": body.target_lang,
        "context_before": before,
        "selection": selection,
        "context_after": after,
    })
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.from_offset,
        to_offset=body.to_offset,
        old_text=selection,
        new_text=new_text,
        source="translate",
        pending_at=datetime.now(timezone.utc),
        metadata={"target_lang": body.target_lang},
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/m5/chapters/{chapter_name}/cite — canonical citations
# ---------------------------------------------------------------------------


class CiteBody(BaseModel):
    at_offset: int
    reference_id: str


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/cite")
def cite_chapter(
    project_id: uuid.UUID,
    chapter_name: str,
    body: CiteBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Insert a canonical citation at a specific offset in chapter prose.

    Decision: cite differs from paraphrase/translate — it's an INSERTION (not
    replacement). from_offset == to_offset == at_offset, old_text="", and
    new_text is " (Author, Year)" with a leading space to ensure whitespace
    between prose and citation. No LLM call — uses build_citation_text(ref).

    The endpoint creates a PendingEdit so the front-end can present an
    accept/reject ribbon before the prose is mutated.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    if body.at_offset < 0 or body.at_offset > len(prose):
        raise HTTPException(400, detail={"error": {"code": "offset_out_of_range"}})
    pool = _collect_reference_pool(cs)
    target = next((r for r in pool if _reference_id(r) == body.reference_id), None)
    if target is None:
        raise HTTPException(404, detail={"error": {"code": "reference_not_found"}})
    citation = " " + build_citation_text(target)
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.at_offset,
        to_offset=body.at_offset,
        old_text="",
        new_text=citation,
        source="cite",
        pending_at=datetime.now(timezone.utc),
        metadata={"reference_id": body.reference_id},
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/m5/chapters/{chapter_name}/pending/{edit_id}/accept
# ---------------------------------------------------------------------------


def _splice(prose: str, from_offset: int, to_offset: int, new_text: str) -> str:
    """Return prose with prose[from_offset:to_offset] replaced by new_text.

    Decision: pure string concat keeps this simple and O(n); no regex so
    special characters in new_text are never misinterpreted.
    """
    return prose[:from_offset] + new_text + prose[to_offset:]


def _find_and_pop_edit(chapter_dict: dict, edit_id: str) -> dict | None:
    """Remove and return the edit with the given id from pending_edits.

    Decision: pop by index so we never iterate the list twice; returns None
    when the id is not found so callers can raise their own 404.
    """
    edits = chapter_dict.get("pending_edits", [])
    for i, e in enumerate(edits):
        if e.get("id") == edit_id:
            return edits.pop(i)
    return None


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/pending/{edit_id}/accept")
def accept_pending_edit(
    project_id: uuid.UUID,
    chapter_name: str,
    edit_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Splice a PendingEdit's new_text into chapter prose and remove the edit.

    Decision: the endpoint peeks (without popping) to validate offsets first.
    If prose[from_offset:to_offset] no longer equals the edit's old_text the
    chapter was mutated after the edit was created; we return 409 stale_offsets
    so the front-end can surface the conflict rather than silently corrupting
    the document.
    """
    from orchestrator.tools.m5_writing import validate_citations_plain  # noqa: PLC0415

    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")

    # Peek without popping to validate offsets first
    edits = ch.get("pending_edits", [])
    target = next((e for e in edits if e.get("id") == edit_id), None)
    if target is None:
        raise HTTPException(404, detail={"error": {"code": "edit_not_found"}})

    from_offset = target["from_offset"]
    to_offset = target["to_offset"]
    # Critical concurrency check: if the prose changed since the edit was created
    # the offsets are stale and splicing would corrupt the document.
    if from_offset > len(prose) or to_offset > len(prose) or prose[from_offset:to_offset] != target["old_text"]:
        raise HTTPException(
            409,
            detail={"error": {"code": "stale_offsets", "edit_id": edit_id}},
        )

    # Offsets validated — now pop and splice
    _find_and_pop_edit(ch, edit_id)
    new_prose = _splice(prose, from_offset, to_offset, target["new_text"])
    ch["prose"] = new_prose

    # Re-validate citations so the chapter's used/uncited lists stay current
    pool = _collect_reference_pool(cs)
    validation = validate_citations_plain(new_prose, pool)
    ch["citations_used"] = validation["citations_used"]
    ch["uncited_warnings"] = validation["uncited_warnings"]

    flag_modified(cs, "m5_writing")
    db.commit()
    return ch

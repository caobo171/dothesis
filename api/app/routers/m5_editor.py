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


def _normalize_stored_chapters(chapters: dict) -> dict | None:
    """Fold retired chapter keys in a stored `chapters` dict onto canonical ones.

    Returns None when there is nothing to do — the overwhelmingly common case —
    so the read path stays a plain read and never commits a no-op write.

    The merge rule itself is NOT restated here: `merge_chapter_prose` owns it
    (a retired key and the canonical key are concatenated, legacy first, never
    picked between). Only the per-chapter bookkeeping the editor cares about is
    reassembled around it: the surviving entry keeps its `pending_edits` and
    `citations_used`, since a pending edit whose offsets no longer line up
    already fails closed with 409 stale_offsets on accept.

    FOLD, NEVER PRUNE. `merge_chapter_prose` returns only the chapters it
    claims — it skips blank prose and anything that is not one of the five — so
    driving the output off its keys made a READ delete persisted state: a
    chapter the student had emptied in the editor, and any non-canonical key a
    producer parked here (`abstract`), vanished on the next open and could not
    be written back (PATCH 404s chapter_not_drafted on a key that is no longer
    stored). Every key the merge does not claim is therefore carried forward
    exactly as stored; only the retired keys move.
    """
    from orchestrator.tools.m5_writing import canonical_chapter, merge_chapter_prose

    # A key is work for us only when it resolves to a DIFFERENT canonical
    # chapter. Already-canonical keys and non-chapters both stay put, so
    # neither is a reason to rewrite (and re-commit) the dict.
    retired = {k: canonical_chapter(k) for k in chapters
               if canonical_chapter(k) and canonical_chapter(k) != k}
    if not retired:
        return None

    def _prose_of(ch):
        return (ch.get("prose") or "") if isinstance(ch, dict) else str(ch or "")

    merged = merge_chapter_prose((k, _prose_of(v)) for k, v in chapters.items())
    # Carry everything forward first, in stored order; the retired keys are the
    # only ones removed, and their prose reappears under the canonical home below.
    out: dict = {k: v for k, v in chapters.items() if k not in retired}
    for name in dict.fromkeys(retired.values()):
        # Prefer the canonical key's own entry for the non-prose fields; fall
        # back to whichever retired key held this chapter when only that exists.
        base = chapters.get(name)
        if not isinstance(base, dict):
            base = next((v for k, v in chapters.items()
                         if k in retired and retired[k] == name and isinstance(v, dict)), {})
        entry = dict(base)
        entry["name"] = name
        # `merged` has no entry when every block folding in here was blank —
        # keep the canonical key anyway, so an emptied Chapter 5 stays an
        # editable, PATCH-able pane instead of disappearing.
        entry["prose"] = merged.get(name, _prose_of(base))
        out[name] = entry
    return out


@router.post("/projects/{project_id}/m5/chapters")
def list_chapters(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Return all chapters from m5_writing.chapters.

    Backfill: a project whose M5 went through the conversational/export path has
    its prose in `final_sections` (a flat list), not `chapters`. Without this the
    editor would open empty for those projects even though a finished DOCX
    exists. We synthesize the canonical chapter dict from `final_sections` and
    persist it once, so the editor, autosave (PATCH), and export all read the
    same `chapters` shape afterwards.

    Normalize-on-read: a PRE-EXISTING `chapters` dict skips that backfill
    entirely, so a pre-branch auto-mode project — which stored all six keys —
    was returned raw. Its `discussion` prose is then invisible and uneditable in
    the editor (OutlineRail knows only the canonical five) while the export path
    still ships it, i.e. editor and exported document disagree about Chapter 5
    for exactly that cohort. Retired keys go through the same helper the
    backfill uses.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    m5 = (cs.m5_writing or {}) if cs else {}
    chapters = m5.get("chapters") or {}
    if chapters:
        normalized = _normalize_stored_chapters(chapters)
        if normalized is not None and cs is not None:
            m5["chapters"] = normalized
            cs.m5_writing = m5
            flag_modified(cs, "m5_writing")
            db.commit()
            return normalized
        return chapters

    final_sections = m5.get("final_sections") or []
    if cs and final_sections:
        from orchestrator.tools.m5_writing import chapters_from_final_sections
        synthesized = chapters_from_final_sections(final_sections)
        if synthesized:
            m5["chapters"] = synthesized
            cs.m5_writing = m5
            flag_modified(cs, "m5_writing")
            db.commit()
            return synthesized
    return {}


# ---------------------------------------------------------------------------
# PATCH /projects/{project_id}/m5/chapters/{chapter_name} — autosave
# ---------------------------------------------------------------------------

# Kept in step with m5_writing.M5_CHAPTER_ORDER by a test in
# orchestrator/tests/test_schemas.py — this is a copy, not a source of truth.
_VALID_CHAPTER_NAMES = {
    "intro", "lit_review", "methodology", "results", "conclusion"
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


@router.post("/projects/{project_id}/m5/references")
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
from orchestrator.tools.m5_inline import paraphrase_selection, translate_selection, rewrite_selection, build_citation_text  # noqa: E402 — translate_selection + build_citation_text reused by Tasks 12+13


class ParaphraseBody(BaseModel):
    from_offset: int
    to_offset: int
    style: str = ""


# The "practical inline actions" (jenni-style) share ONE endpoint shape: rewrite
# the selection per a fixed instruction, wrap it in a PendingEdit. The kind is
# the URL segment; the instruction is what actually differs. Kept as data here
# so a new action is one line, and the PendingEditSource literal is the single
# gate on which kinds exist.
class RewriteBody(BaseModel):
    from_offset: int
    to_offset: int


_INLINE_INSTRUCTIONS: dict[str, str] = {
    "proofread": (
        "Fix grammar, spelling, punctuation, and awkward word choice. Do NOT "
        "change the meaning, terminology, numbers, or citations. Stay as close "
        "to the original wording as the corrections allow."
    ),
    "improve": (
        "Rewrite in a stronger, more formal academic voice — precise, objective, "
        "and well structured — while preserving the meaning, numbers, and "
        "citations."
    ),
    "humanize": (
        "Rewrite so it reads as natural human academic writing rather than "
        "AI-generated prose: vary the sentence rhythm and remove formulaic "
        "phrasing and filler. Do NOT change the meaning, numbers, or citations."
    ),
    "expand": (
        "Expand the selection with more detail, explanation, or supporting "
        "reasoning, staying on topic and in the same academic register. Do NOT "
        "invent citations or fabricate data."
    ),
    "shorten": (
        "Make the selection more concise — cut redundancy and filler while "
        "keeping all substantive content, numbers, and citations."
    ),
}


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
# Practical inline actions (jenni-style): proofread / improve / humanize /
# expand / shorten. Same shape as paraphrase — rewrite the selection per a fixed
# instruction and return a PendingEdit — so one helper backs all five.
# ---------------------------------------------------------------------------
def _rewrite_selection_edit(
    kind: str, project_id: uuid.UUID, chapter_name: str, body: RewriteBody,
    user: User, db: Session,
) -> dict:
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    _validate_range(prose, body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    language = ((cs.m1_topic or {}).get("language", "en")) if cs else "en"
    new_text = rewrite_selection.invoke({
        "chapter_name": chapter_name,
        "language": language,
        "context_before": before,
        "selection": selection,
        "context_after": after,
        "instruction": _INLINE_INSTRUCTIONS[kind],
    })
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.from_offset,
        to_offset=body.to_offset,
        old_text=selection,
        new_text=new_text,
        source=kind,
        pending_at=datetime.now(timezone.utc),
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/proofread")
def proofread_chapter_selection(
    project_id: uuid.UUID, chapter_name: str, body: RewriteBody,
    user: User = Depends(current_user), db: Session = Depends(db_session),
):
    """Fix grammar/punctuation/word-choice in a selection → PendingEdit."""
    return _rewrite_selection_edit("proofread", project_id, chapter_name, body, user, db)


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/improve")
def improve_chapter_selection(
    project_id: uuid.UUID, chapter_name: str, body: RewriteBody,
    user: User = Depends(current_user), db: Session = Depends(db_session),
):
    """Rewrite a selection in a stronger academic voice → PendingEdit."""
    return _rewrite_selection_edit("improve", project_id, chapter_name, body, user, db)


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/humanize")
def humanize_chapter_selection(
    project_id: uuid.UUID, chapter_name: str, body: RewriteBody,
    user: User = Depends(current_user), db: Session = Depends(db_session),
):
    """Rewrite AI-sounding prose in a selection into a natural voice → PendingEdit."""
    return _rewrite_selection_edit("humanize", project_id, chapter_name, body, user, db)


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/expand")
def expand_chapter_selection(
    project_id: uuid.UUID, chapter_name: str, body: RewriteBody,
    user: User = Depends(current_user), db: Session = Depends(db_session),
):
    """Expand a selection with more detail → PendingEdit."""
    return _rewrite_selection_edit("expand", project_id, chapter_name, body, user, db)


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/shorten")
def shorten_chapter_selection(
    project_id: uuid.UUID, chapter_name: str, body: RewriteBody,
    user: User = Depends(current_user), db: Session = Depends(db_session),
):
    """Make a selection more concise → PendingEdit."""
    return _rewrite_selection_edit("shorten", project_id, chapter_name, body, user, db)


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

    # Critical correctness guard: verify the edit's stored chapter_name matches
    # the URL's chapter_name. If a bug ever places an edit in the wrong chapter's
    # pending_edits, this prevents silently consuming it via the wrong URL.
    if target.get("chapter_name") != chapter_name:
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


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/m5/chapters/{chapter_name}/pending/{edit_id}/reject
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/pending/{edit_id}/reject")
def reject_pending_edit(
    project_id: uuid.UUID,
    chapter_name: str,
    edit_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Drop a PendingEdit without touching prose or validating offsets.

    Decision: simpler than accept — no offset check, no prose mutation.
    The edit is removed from pending_edits and the chapter is returned unchanged.
    Peek (without popping) to validate chapter_name ownership before any mutation,
    mirroring the "don't mutate before validation" semantics of the accept endpoint.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    # Peek first to validate existence and chapter_name ownership before mutating.
    edits = ch.get("pending_edits", [])
    target = next((e for e in edits if e.get("id") == edit_id), None)
    if target is None:
        raise HTTPException(404, detail={"error": {"code": "edit_not_found"}})
    # Critical correctness guard: verify the edit's stored chapter_name matches
    # the URL's chapter_name. Prevents consuming an edit via the wrong chapter URL.
    if target.get("chapter_name") != chapter_name:
        raise HTTPException(404, detail={"error": {"code": "edit_not_found"}})
    _find_and_pop_edit(ch, edit_id)
    flag_modified(cs, "m5_writing")
    db.commit()
    return ch


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/m5/export — re-run compile_pdf + export_docx
# ---------------------------------------------------------------------------

from orchestrator.tools.m5_writing import (  # noqa: E402
    M5_CHAPTER_ORDER as _REQUIRED_CHAPTERS,
    run_export,
    sections_from_m5_slice,
)


@router.post("/projects/{project_id}/m5/export")
def reexport(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Re-run docx + pdf export on the current chapter prose.

    Decision: the endpoint is intentionally idempotent — every POST replaces
    the stored export_artifacts with fresh S3 artifacts. This lets the user
    re-export after editing without any state cleanup.

    Returns {"docx": artifact, "pdf": artifact} where each artifact has
    kind, s3_key, size_bytes, download_url, and uri fields.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    m5 = (cs.m5_writing or {}) if cs else {}

    # run_export + sections_from_m5_slice are the single shared export path
    # (same one the auto-export hook and the agent's export tool use), so the
    # artifact shape + download URL can't drift across the three callers.
    # `language` is read up here because the chapter HEADINGS need it too, not
    # only the cover/TOC that run_export localizes; it is the fallback for prose
    # too short to read (sections_from_m5_slice detects from the prose first).
    # (Guarded on `cs` because this now runs BEFORE the no-chapters 400 that
    # used to be the only thing standing between a missing row and this read.)
    m1 = (cs.m1_topic or {}) if cs else {}
    language = m1.get("language") or "vi"
    sections = sections_from_m5_slice(m5, language=language)

    # A docx should be producible AT ANY POINT — the thesis is written chapter by
    # chapter as each module (M1→M5) completes, not only once all five exist. So
    # we export whatever chapters carry prose and only refuse when there is
    # nothing at all to render. (Was: hard 400 unless all six chapters present —
    # pre-five-chapter-collapse, which forced the user to "finish M5" before any
    # export.) `missing` is still returned so the client can show what's left to
    # draft.
    missing = [n for n in _REQUIRED_CHAPTERS if n not in (m5.get("chapters") or {})]
    if not sections:
        raise HTTPException(400, detail={"error": {"code": "no_chapters_yet", "missing": missing}})
    references = (cs.m2_literature or {}).get("literature_sources") or []
    artifacts = run_export(sections, str(project_id), references=references, language=language,
                           title=m1.get("research_title"))

    m5["export_artifacts"] = artifacts
    cs.m5_writing = m5
    flag_modified(cs, "m5_writing")
    db.commit()

    # `missing` lets the UI say "exported 4 of 5 chapters — Conclusion still to
    # draft" instead of implying the doc is complete.
    return {"docx": artifacts[0], "pdf": artifacts[1], "missing_chapters": missing}

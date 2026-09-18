"""SP6.5: editor API — chapter prose CRUD, inline AI tools, accept/reject."""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import logging
import math
import mimetypes
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from orchestrator.tools.research_cache import cached_call

from ..db import db_session, get_session_factory
from ..deps import current_user
from ..agent_state import nested_slices
from ..models import ContextStore, Export, Project, User

router = APIRouter(tags=["m5_editor"])
logger = logging.getLogger(__name__)


_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _data_image(path: str) -> str | None:
    """Encode a localised artifact for the authenticated editor response."""
    try:
        file = Path(path)
        if not file.is_file() or file.stat().st_size <= 0:
            return None
        mime = mimetypes.guess_type(file.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode('ascii')}"
    except OSError:
        return None


def _chapter_media_previews(chapters: dict, cs: ContextStore | None) -> dict:
    """Attach transient browser previews without changing stored markdown.

    Chapter prose intentionally keeps exporter-readable local/S3 image paths.
    Browsers cannot read either. The response therefore carries a reversible
    source-to-data-URL mapping; the web editor swaps it only for display and
    maps it back before autosave.
    """
    if not chapters:
        return chapters

    m4 = (cs.m4_analysis or {}) if cs else {}
    analysis = m4.get("analysis_results") or m4.get("results") or {}
    figures = analysis.get("source_figures") if isinstance(analysis, dict) else {}
    durable: dict[str, str] = {}
    if isinstance(figures, dict):
        from orchestrator.tools.figure_store import localize
        for uri in figures.values():
            local = localize(str(uri or ""))
            if local:
                durable[Path(local).name] = local

    response: dict = {}
    for name, raw in chapters.items():
        entry = dict(raw) if isinstance(raw, dict) else {"name": name, "prose": str(raw or "")}
        prose = str(entry.get("prose") or "")
        sources = _MARKDOWN_IMAGE_RE.findall(prose)
        media = []
        for source in sources:
            local = source if Path(source).is_file() else durable.get(Path(source).name)
            preview = _data_image(local) if local else None
            if preview:
                media.append({"source": source, "preview_url": preview})

        # A model image is generated into scratch storage. If that file has
        # expired, rebuild the same structured M3 artifact for preview only;
        # the original source string remains in prose and therefore in saves.
        if name == "methodology" and len(media) < len(sources):
            m3 = (cs.m3_design or {}) if cs else {}
            conceptual_model = m3.get("conceptual_model") if isinstance(m3, dict) else None
            if conceptual_model:
                from orchestrator.tools.m5_writing import _pillow_model_figure
                generated = _pillow_model_figure(conceptual_model, "vi")
                generated_sources = _MARKDOWN_IMAGE_RE.findall(generated or "")
                generated_preview = _data_image(generated_sources[0]) if generated_sources else None
                if generated_preview:
                    mapped = {item["source"] for item in media}
                    for source in sources:
                        if source not in mapped:
                            media.append({"source": source, "preview_url": generated_preview})
        entry["media"] = media
        # Tell the editor which placement tokens can actually be materialised
        # from verified state. A token is retained for future data, but the UI
        # must not promise "generated at export" when export will correctly
        # remove it rather than fabricate a table.
        renderable: set[str] = set()
        try:
            from orchestrator.tools.results_render import (
                render_cleaning_section, render_limitations, render_results_tables,
            )
            if name == "methodology":
                block = render_cleaning_section(analysis, "vi")
                if block:
                    renderable.add(block["kind"])
            elif name == "results":
                renderable.update(
                    block["kind"] for block in render_results_tables(analysis, "vi", host_prose=prose)
                )
            elif name == "conclusion":
                nested = {
                    "m3_design": (cs.m3_design or {}) if cs else {},
                    "m4_analysis": {"analysis_results": analysis},
                }
                block = render_limitations(nested, language="vi")
                if block:
                    renderable.add(block["kind"])
        except Exception:
            # Preview metadata is advisory; chapter reading must remain fail-open.
            pass
        entry["renderable_tokens"] = sorted(renderable)
        # Transient optimistic-concurrency token, never stored in the markdown.
        # It makes a proposal reject if another edit moved a zero-width citation
        # insertion while its selected range still happens to be empty.
        entry["document_fingerprint"] = _chapter_fingerprint(prose)
        response[name] = entry
    return response


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    """Reuse the SP6 exports.py pattern: 404 (not 403) to avoid existence leaks."""
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found"}})
    return p


def _chapter_fingerprint(prose: str) -> str:
    return hashlib.sha256(prose.encode("utf-8")).hexdigest()


def _m5_slice(db: Session, project_id: uuid.UUID) -> dict:
    """Return the m5_writing JSONB blob, or {} if not yet seeded."""
    cs = db.get(ContextStore, project_id)
    return (cs.m5_writing or {}) if cs else {}


class ReviewBody(BaseModel):
    kind: str = "peer_review"


class ReferenceSearchBody(BaseModel):
    query: str
    limit: int = 10


class AddReferenceBody(BaseModel):
    doi: str | None = None
    title: str | None = None


def _normalized_doi(value: object) -> str:
    """Canonical DOI identity; display URLs are deliberately not identities."""
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value or "").strip(), flags=re.I).lower()


def _normalized_title(value: object) -> str:
    """Stable fallback identity for sources without a DOI."""
    return re.sub(r"[^\w]+", "", str(value or "").casefold())


def _paper_key(paper: dict) -> str:
    doi = _normalized_doi(paper.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = _normalized_title(paper.get("title"))
    if title:
        # Editions and conference revisions can share a title without a DOI.
        # Bibliographic author/year keeps them distinct while still collapsing
        # duplicate provider records for the same work.
        return f"title:{title}|{_reference_author(paper).casefold()}|{str(paper.get('year') or '').strip()}"
    # Imported pre-editor records sometimes only have an author/year. Keep
    # their old selection surface working, but never pretend this is unique.
    return f"legacy:{_reference_author(paper).casefold()}|{str(paper.get('year') or '').strip()}"


_TRUSTED_INDEX_PROVIDERS = {"OpenAlex", "Crossref"}
_TRUSTED_INDEX_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)


def _index_identity(paper: dict) -> dict | None:
    """Return complete identity only for a row produced by a trusted adapter."""
    if paper.get("provider") not in _TRUSTED_INDEX_PROVIDERS:
        return None
    doi = _normalized_doi(paper.get("doi"))
    title = str(paper.get("title") or "").strip()
    authors = paper.get("authors")
    if isinstance(authors, str):
        authors = [authors]
    authors = [author.strip() for author in authors if isinstance(author, str) and author.strip()] if isinstance(authors, (list, tuple)) else []
    try:
        year = int(paper.get("year"))
    except (TypeError, ValueError):
        return None
    if (not _TRUSTED_INDEX_DOI.fullmatch(doi) or not title or not any(authors)
            or year < 1600 or year > datetime.now(timezone.utc).year + 1):
        return None
    return {"doi": doi, "title": title, "authors": authors, "year": year}


def _identity_conflicts(rows: list[dict]) -> bool:
    """Fail closed when merged same-DOI metadata disagrees materially."""
    titles = {_normalized_title(row.get("title")) for row in rows if str(row.get("title") or "").strip()}
    years = {str(row.get("year")).strip() for row in rows if row.get("year") not in (None, "")}
    author_sets = {
        tuple(re.sub(r"\W+", "", str(author).casefold()) for author in (row.get("authors") or []) if str(author).strip())
        for row in rows if isinstance(row.get("authors"), (list, tuple)) and row.get("authors")
    }
    return len(titles) > 1 or len(years) > 1 or len(author_sets) > 1


def _trusted_index_marker(rows: list[dict]) -> dict | None:
    """Attach server-derived identity metadata after provider rows are merged."""
    identities = [identity for row in rows if (identity := _index_identity(row))]
    if not identities:
        return None
    return {"identity": identities[0], "conflict": _identity_conflicts(rows)}


def _paper_score(paper: dict, query: str) -> float:
    """Transparent ranking for the editor search results.

    Title overlap carries most of the relevance signal; abstract overlap helps
    claim-level searches, and citation count is log-scaled so famous but weakly
    related papers cannot drown out a close topical match.
    """
    words = {w for w in re.findall(r"[\wÀ-ỹ]{3,}", query.lower())}
    title = str(paper.get("title") or "").lower()
    abstract = str(paper.get("abstract") or "").lower()
    title_hits = sum(1 for w in words if w in title)
    abstract_hits = sum(1 for w in words if w in abstract)
    citations = int(paper.get("citation_count") or 0)
    return title_hits * 5 + abstract_hits * 1.25 + math.log10(citations + 1)


def _crossref_paper_search(query: str, limit: int) -> list[dict]:
    """Reliable third leg for editor search when free indexes rate-limit."""
    import httpx  # local: keeps editor import/startup light
    response = httpx.get(
        "https://api.crossref.org/works",
        params={
            "query.bibliographic": query,
            "rows": limit,
            "select": "title,author,issued,DOI,container-title,URL,abstract,is-referenced-by-count",
            "filter": "type:journal-article",
        },
        headers={"User-Agent": "DoThesis/1.0 (mailto:dothesis@users.noreply.github.com)"},
        timeout=14,
    )
    response.raise_for_status()
    out = []
    for item in response.json().get("message", {}).get("items", []):
        title = str((item.get("title") or [""])[0]).strip()
        date_parts = item.get("issued", {}).get("date-parts") or [[None]]
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        authors = [str(a.get("family") or "").strip() for a in item.get("author", [])]
        authors = [a for a in authors if a]
        if not title or not authors or not year:
            continue
        abstract = re.sub(r"<[^>]+>", " ", str(item.get("abstract") or ""))
        abstract = re.sub(r"\s+", " ", abstract).strip()
        out.append({
            "title": title, "authors": authors, "year": year,
            "doi": item.get("DOI"), "url": item.get("URL"),
            "journal": (item.get("container-title") or [None])[0],
            "abstract": abstract,
            "citation_count": int(item.get("is-referenced-by-count") or 0),
            "source_type": "journal", "confidence": 0.9 if item.get("DOI") else 0.7,
        })
    return out


def _cached_editor_provider_search(provider: str, query: str, limit: int, compute) -> list[dict]:
    """Cache only non-empty raw provider rows under a non-secret stable key.

    The persistent cache hashes this key before writing it.  Keeping provider
    payloads separate avoids treating a Crossref row as an OpenAlex response,
    whose metadata shapes and freshness characteristics differ.
    """
    key = {"provider": provider, "query": " ".join(query.casefold().split()), "limit": limit}
    return cached_call(
        "scholarly-search-v1", key, compute, ttl_s=7 * 86400,
        cache_if=lambda rows: isinstance(rows, list) and bool(rows),
    )


def search_scholarly_references(query: str, limit: int = 5) -> dict:
    """Run a read-only scholarly lookup without project or database access.

    The editor endpoint owns authorization. Claim review can safely call this
    pure provider helper from bounded workers without sharing its SQLAlchemy
    session across threads.
    """
    query = str(query or "").strip()
    if len(query) < 3:
        raise ValueError("query_too_short")
    limit = max(3, min(int(limit), 20))

    from engine.utils.api_citations.openalex import OpenAlexClient
    from engine.utils.api_citations.semantic_scholar import SemanticScholarClient

    def openalex():
        return _cached_editor_provider_search(
            "openalex", query, limit,
            lambda: OpenAlexClient(timeout=10, max_retries=1).search_papers(query, limit=limit),
        )

    def semantic():
        return _cached_editor_provider_search(
            "semantic_scholar", query, limit,
            lambda: SemanticScholarClient(timeout=10, max_retries=1).search_papers(query, limit=limit),
        )

    def crossref():
        return _cached_editor_provider_search(
            "crossref", query, limit, lambda: _crossref_paper_search(query, limit),
        )

    rows: list[dict] = []
    providers: list[str] = []
    responded_providers: list[str] = []
    # One slow/rate-limited provider must not block useful results from the
    # other. Each client already fails closed to [], so partial success is a
    # normal response and the UI reports which indexes answered.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    try:
        futures = {
            pool.submit(openalex): "OpenAlex",
            pool.submit(semantic): "Semantic Scholar",
            pool.submit(crossref): "Crossref",
        }
        done, _ = concurrent.futures.wait(futures, timeout=14)
        for future, provider in futures.items():
            if future not in done:
                future.cancel()
                logger.warning("editor reference search timed out for %s", provider)
                continue
            try:
                found = future.result() or []
                responded_providers.append(provider)
                if found:
                    providers.append(provider)
                for paper in found:
                    rows.append({**paper, "provider": provider})
            except Exception:
                logger.exception("editor reference search failed for %s", provider)
    finally:
        # Do not let a misbehaving remote client turn the caller's timeout
        # into a hidden executor-context wait. Provider clients have their own
        # network limits and any stragglers cannot mutate this response.
        pool.shutdown(wait=False, cancel_futures=True)

    grouped: dict[str, list[dict]] = {}
    for paper in rows:
        key = _paper_key(paper)
        if key.endswith("title:"):
            continue
        grouped.setdefault(key, []).append(paper)

    deduped: dict[str, dict] = {}
    for key, variants in grouped.items():
        # Keep Semantic Scholar's richer abstract when it wins ranking, while
        # carrying only a separately derived trusted index identity marker.
        selected = max(variants, key=lambda paper: len(str(paper.get("abstract") or "")))
        marker = _trusted_index_marker(variants)
        deduped[key] = {**selected, **({"_identity_from_index": marker} if marker else {})}

    ranked = sorted(deduped.values(), key=lambda p: _paper_score(p, query), reverse=True)[:limit]
    results = []
    for paper in ranked:
        abstract = str(paper.get("abstract") or "").strip()
        results.append({
            "id": _reference_id(paper),
            "title": paper.get("title"),
            "authors": paper.get("authors") or [],
            "author": _reference_author(paper),
            "year": paper.get("year"),
            "venue": paper.get("journal") or paper.get("venue"),
            "doi": paper.get("doi"),
            "url": paper.get("url"),
            "abstract": abstract,
            "abstract_preview": abstract[:360],
            "citation_count": int(paper.get("citation_count") or 0),
            # Search indexes expose candidate metadata only. A DOI string is
            # useful for the follow-up lookup, but becomes `verified: true`
            # only after `/references/add` resolves this exact selected source.
            "verified": False,
            "doi_available": bool(_normalized_doi(paper.get("doi"))),
            "provider": paper.get("provider"),
            "relevance_score": round(_paper_score(paper, query), 2),
            # Internal server provenance. The claim-review worker may opt in
            # only after this helper created it; browser add-reference flows
            # never treat it as a substitute for exact resolver verification.
            "_identity_from_index": paper.get("_identity_from_index"),
        })
    return {"results": results, "count": len(results), "providers": providers,
            "responded_providers": responded_providers, "query": query}


@router.post("/projects/{project_id}/m5/references/search")
def search_editor_references(
    project_id: uuid.UUID,
    body: ReferenceSearchBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Search academic indexes after enforcing the project boundary."""
    _owned_project(db, user, project_id)
    try:
        result = search_scholarly_references(body.query, body.limit)
        # Provider-derived identity provenance is for the in-process claim
        # worker. Do not expose it as a browser-selectable verification flag.
        result["results"] = [{key: value for key, value in paper.items() if key != "_identity_from_index"}
                             for paper in result["results"]]
        return result
    except ValueError as exc:
        if str(exc) == "query_too_short":
            raise HTTPException(400, detail={"error": {"code": "query_too_short"}}) from exc
        raise


@router.post("/projects/{project_id}/m5/references/add")
def add_editor_reference(
    project_id: uuid.UUID,
    body: AddReferenceBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Verify one selected search result and add it through commit_slice."""
    _owned_project(db, user, project_id)
    lookup = (body.doi or body.title or "").strip()
    if not lookup:
        raise HTTPException(400, detail={"error": {"code": "reference_identifier_required"}})

    from engine.utils.api_citations.openalex import OpenAlexClient
    from engine.utils.api_citations import CrossrefClient

    verified = None
    doi = _normalized_doi(body.doi)
    if doi:
        verified = OpenAlexClient(timeout=10, max_retries=1).get_paper_by_doi(doi)
        if not verified:
            verified = CrossrefClient().search_paper(doi)
        # A result that happens to have a DOI is not verification of the DOI
        # the student chose. Near matches would poison the project library.
        if not verified or _normalized_doi(verified.get("doi")) != doi:
            raise HTTPException(422, detail={"error": {"code": "reference_not_verified"}})
    else:
        verified = CrossrefClient().search_paper(lookup)
        # A title-only request has no immutable external identifier, so accept
        # only a strict normalized title match rather than a ranked near match.
        if not verified or _normalized_title(verified.get("title")) != _normalized_title(lookup):
            raise HTTPException(422, detail={"error": {"code": "reference_not_verified"}})
    if not verified or not verified.get("title"):
        raise HTTPException(422, detail={"error": {"code": "reference_not_verified"}})
    verified["verified"] = True

    cs = db.get(ContextStore, project_id)
    current = list(((cs.m2_literature or {}).get("literature_sources") or []) if cs else [])
    target_key = _paper_key(verified)
    existing = next((source for source in current if _paper_key(source) == target_key), None)
    if existing is None:
        from ..agent_state import DbProjectStateStore
        store = DbProjectStateStore(db.get_bind(), project_id, Path("."))
        store.user_id = user.id
        try:
            commit = store.commit_slice(
                "M2", {"literature_sources": current + [verified]},
                reason="Student added a verified paper from editor search",
                confirm_done=False,
            )
            if not isinstance(commit, dict) or commit.get("error"):
                raise RuntimeError(f"M2 commit rejected: {commit!r}")
        except Exception:
            # Never return a successful add when the only legal state write
            # failed; the student can retry without a phantom library source.
            logger.exception("editor reference add commit failed")
            raise HTTPException(500, detail={"error": {"code": "reference_add_failed"}})
        source = verified
    else:
        source = existing
    return {**source, "id": _reference_id(source), "author": _reference_author(source)}


@router.post("/projects/{project_id}/m5/review")
def review_thesis_document(
    project_id: uuid.UUID,
    body: ReviewBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Run the existing committee-readiness rubric from the editor.

    Decision: this is read-only over the project-scoped context store. The
    editor and chat `review_thesis` tool therefore grade the same chapters,
    citations, statistics, advisor comments and institutional requirements;
    there is no second, UI-only reviewer that can drift from the agent.
    """
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    if cs is None or not (cs.m5_writing or {}).get("chapters"):
        raise HTTPException(400, detail={"error": {"code": "no_chapters_yet"}})

    from quality.rubric import focused_review

    allowed = {"claim_confidence", "peer_review", "source_quality", "tone_of_voice", "proofread"}
    if body.kind not in allowed:
        raise HTTPException(400, detail={"error": {"code": "unknown_review_kind"}})

    context = nested_slices(cs)
    coaching = cs.coaching or {}
    result = focused_review(
        context,
        body.kind,
        institution_profile=coaching.get("institution_profile") or None,
        advisor_feedback=coaching.get("advisor_feedback") or [],
    )
    return {
        **result,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "review_id": str(uuid.uuid4()),
        "review_kind": body.kind,
    }


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
    stored = m5.get("chapters") or {}
    # `_normalize_stored_chapters` returns None when there is nothing to fold.
    chapters = (_normalize_stored_chapters(stored) if stored else {})
    if chapters is None:
        chapters = dict(stored)

    # Backfill whatever `chapters` is MISSING, not only the all-or-nothing case.
    #
    # This used to be `if chapters: return it` — a non-empty dict skipped the
    # backfill entirely. Chapters are composed per module as each one finishes,
    # and only some paths write the editor's dict, so a real project reached the
    # editor holding intro/lit_review/conclusion in `chapters` and methodology
    # and results only in `final_sections`. The outline greyed both out: two
    # finished chapters, 45k characters, invisible and uneditable — while the
    # export path read `final_sections` and shipped them. Editor and document
    # disagreeing about which chapters exist is the same class of bug the
    # normalize-on-read above was written for.
    #
    # Existing entries always win: the student may have edited them, and
    # `final_sections` is a snapshot from whenever it was last composed.
    final_sections = m5.get("final_sections") or []
    added = False
    if final_sections:
        from orchestrator.tools.m5_writing import chapters_from_final_sections
        for name, body in (chapters_from_final_sections(final_sections) or {}).items():
            if name not in chapters and body:
                chapters[name] = body
                added = True

    if cs is not None and (added or chapters != stored):
        m5["chapters"] = chapters
        cs.m5_writing = m5
        flag_modified(cs, "m5_writing")
        db.commit()
    return _chapter_media_previews(chapters, cs)


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
    expected_document_fingerprint: str | None = None


def _reference_author(ref: dict) -> str:
    """Return the citation/display author for either current or legacy M2 data."""
    authors = ref.get("authors")
    if isinstance(authors, list) and authors:
        first = str(authors[0]).strip()
        surname = first.split()[-1] if first else ""
        if surname:
            return f"{surname} et al." if len(authors) > 1 else surname
    return str(ref.get("author") or "").strip() or "Anon"


def _collect_reference_pool(cs: ContextStore) -> list[dict]:
    """Collect the canonical M2 sources, plus references embedded in legacy gaps.

    Decision: ``literature_sources`` is the project-level source of truth and is
    what the roadmap displays. Older projects may only carry papers inside
    ``research_gaps``, so retain that path as a compatibility fallback/addition.
    Dedupe by (author, year) while preserving canonical-source order.
    """
    m2 = (cs.m2_literature or {}) if cs else {}
    seen: dict[str, dict] = {}
    for paper in m2.get("literature_sources", []) or []:
        key = _paper_key(paper)
        if key.startswith("legacy:"):
            # Without DOI/title there is no evidence these records denote the
            # same work. Retain each one so cite can reject their shared legacy
            # id explicitly instead of silently choosing the first.
            key = f"{key}#{len(seen)}"
        if key not in seen:
            seen[key] = paper
    for gap in m2.get("research_gaps", []) or []:
        for paper in (gap.get("supporting_papers") or []):
            key = _paper_key(paper)
            if key.startswith("legacy:"):
                key = f"{key}#{len(seen)}"
            if key not in seen:
                seen[key] = paper
    return list(seen.values())


def _commit_editor_chapters(
    db: Session, user: User, project_id: uuid.UUID, chapters: dict, reason: str,
) -> None:
    """Persist editor prose through the one M5 state-write boundary.

    The editor used to assign JSONB directly, bypassing focus, snapshot and
    downstream semantics. Passing the full canonical chapter map avoids a
    lossy per-chapter merge while `commit_slice` retains unrelated M5 keys.
    """
    from ..agent_state import DbProjectStateStore

    store = DbProjectStateStore(db.get_bind(), project_id, Path("."))
    store.user_id = user.id
    try:
        from agent.coherence import validate_m5_sections  # noqa: PLC0415
        coherence = validate_m5_sections(chapters, (store.load() or {}).get("contextStore", {}))
        if not coherence.get("crashed") and coherence.get("hard", 0):
            hard = coherence.get("findings_hard") or [
                f for f in coherence.get("findings", []) if f.get("severity") == "hard"
            ]
            raise HTTPException(422, detail={"error": {
                "code": "coherence_violation", "findings": hard,
            }})
    except HTTPException:
        raise
    except Exception:
        # The established coherence boundary fails open when its optional
        # validator cannot run; a broken advisory dependency must not eat prose.
        logger.exception("editor coherence validation unavailable; saving fail-open")
    try:
        committed = store.commit_slice("M5", {"chapters": chapters}, reason=reason, confirm_done=False)
    except Exception:
        logger.exception("editor M5 chapter commit failed")
        raise HTTPException(500, detail={"error": {"code": "chapter_save_failed"}})
    if not isinstance(committed, dict) or committed.get("error"):
        logger.error("editor M5 chapter commit rejected: %r", committed)
        raise HTTPException(500, detail={"error": {"code": "chapter_save_failed"}})


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

    current_prose = str(chapters[chapter_name].get("prose") or "")
    if (body.expected_document_fingerprint
            and body.expected_document_fingerprint != _chapter_fingerprint(current_prose)):
        raise HTTPException(409, detail={"error": {"code": "stale_document"}})

    # Re-validate citations so the front-end always has fresh used/uncited lists
    from orchestrator.tools.m5_writing import validate_citations_plain
    pool = _collect_reference_pool(cs)
    validation = validate_citations_plain(body.prose, pool)

    chapters[chapter_name]["prose"] = body.prose
    chapters[chapter_name]["citations_used"] = validation["citations_used"]
    chapters[chapter_name]["uncited_warnings"] = validation["uncited_warnings"]
    chapters[chapter_name]["ambiguous_citation_warnings"] = validation["ambiguous_warnings"]
    _commit_editor_chapters(db, user, project_id, chapters, "Student autosaved chapter prose")
    return {**chapters[chapter_name], "document_fingerprint": _chapter_fingerprint(body.prose)}


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/m5/references — M2 reference pool with stable ids
# ---------------------------------------------------------------------------


def _reference_id(ref: dict) -> str:
    """Stable source id based on DOI/title, never merely rendered author/year."""
    raw = _paper_key(ref).encode("utf-8")
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
    # Current M2 records use ``authors: list[str]`` while the editor's compact
    # wire contract uses a ready-to-render singular ``author`` label.
    ids = [_reference_id(r) for r in pool]
    return [
        {**r, "id": source_id, "author": _reference_author(r),
         "ambiguous": ids.count(source_id) > 1}
        for r, source_id in zip(pool, ids)
    ]


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/m5/chapters/{chapter_name}/paraphrase
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402 — stdlib, safe to re-import
from uuid import uuid4  # noqa: E402

from orchestrator.schemas.m5_editor import PendingEdit  # noqa: E402
from orchestrator.tools.m5_inline import paraphrase_selection, translate_selection, rewrite_selection, stream_rewrite_selection, build_citation_text  # noqa: E402 — translate_selection + build_citation_text reused by Tasks 12+13
from ..sse import sse_pack  # noqa: E402


class ParaphraseBody(BaseModel):
    from_offset: int
    to_offset: int
    style: str = ""
    prompt: str = Field(default="", max_length=2000)
    expected_document_fingerprint: str | None = None


# The "practical inline actions" (jenni-style) share ONE endpoint shape: rewrite
# the selection per a fixed instruction, wrap it in a PendingEdit. The kind is
# the URL segment; the instruction is what actually differs. Kept as data here
# so a new action is one line, and the PendingEditSource literal is the single
# gate on which kinds exist.
class RewriteBody(BaseModel):
    from_offset: int
    to_offset: int
    prompt: str = Field(default="", max_length=2000)
    expected_document_fingerprint: str | None = None


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


_EDIT_EXPLANATIONS: dict[str, str] = {
    "paraphrase": "Diễn đạt lại để câu văn tự nhiên và học thuật hơn, đồng thời giữ nguyên ý nghĩa, số liệu và trích dẫn.",
    "proofread": "Sửa ngữ pháp, chính tả, dấu câu và cách dùng từ chưa tự nhiên mà không làm thay đổi nội dung học thuật.",
    "improve": "Tăng độ chính xác, mạch lạc và trang trọng của văn phong học thuật; giữ nguyên luận điểm, số liệu và trích dẫn.",
    "humanize": "Giảm cách diễn đạt máy móc và lặp cấu trúc để đoạn văn có nhịp điệu tự nhiên hơn nhưng không đổi hàm ý.",
    "expand": "Bổ sung giải thích và liên kết lập luận để ý chính đầy đủ hơn, không tự tạo dữ liệu hoặc nguồn mới.",
    "shorten": "Loại bỏ phần lặp và từ đệm để câu cô đọng hơn, đồng thời giữ lại toàn bộ nội dung có ý nghĩa.",
    "translate": "Chuyển ngữ đoạn đã chọn và giữ nguyên thuật ngữ chuyên môn, số liệu cùng trích dẫn.",
    "cite": "Chèn trích dẫn từ thư viện nguồn của dự án tại vị trí đã chọn.",
}


def _proposal_metadata(kind: str, started: float, extra: dict | None = None) -> dict:
    """Build the review metadata displayed with a PendingEdit.

    Decision: the rationale is deliberately bounded and action-specific. The
    proposed text already contains the model's substantive work; a second LLM
    call just to narrate it would double latency/cost and could invent a reason
    unrelated to the actual diff.
    """
    return {
        **(extra or {}),
        "explanation": _EDIT_EXPLANATIONS.get(kind, _EDIT_EXPLANATIONS["improve"]),
        "processing_ms": max(1, round((time.perf_counter() - started) * 1000)),
    }


def _validate_range(prose: str, from_offset: int, to_offset: int) -> None:
    """Raise 400 when the selection window is outside the current prose length.

    Decision: guard fires before any LLM call to avoid paying API cost on
    invalid input. from_offset == to_offset is allowed (insertion point).
    """
    if from_offset < 0 or to_offset < from_offset or to_offset > len(prose):
        raise HTTPException(400, detail={"error": {"code": "offset_out_of_range"}})


def _validate_nonempty_selection(from_offset: int, to_offset: int) -> None:
    """Reject collapsed rewrite ranges before they incur an LLM call."""
    if from_offset == to_offset:
        raise HTTPException(400, detail={"error": {"code": "empty_selection"}})


def _validate_document_precondition(prose: str, expected: str | None) -> None:
    if expected and expected != _chapter_fingerprint(prose):
        raise HTTPException(409, detail={"error": {"code": "stale_document"}})


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
    _validate_document_precondition(prose, body.expected_document_fingerprint)
    _validate_range(prose, body.from_offset, body.to_offset)
    _validate_nonempty_selection(body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    language = ((cs.m1_topic or {}).get("language", "en")) if cs else "en"
    started = time.perf_counter()
    new_text = paraphrase_selection.invoke({
        "chapter_name": chapter_name,
        "language": language,
        "context_before": before,
        "selection": selection,
        "context_after": after,
        "style": body.prompt.strip() or body.style,
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
        metadata=_proposal_metadata("paraphrase", started, {
            **({"style": body.prompt.strip() or body.style} if body.prompt.strip() or body.style else {}),
            "document_fingerprint": _chapter_fingerprint(prose),
        }),
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
    _validate_document_precondition(prose, body.expected_document_fingerprint)
    _validate_range(prose, body.from_offset, body.to_offset)
    _validate_nonempty_selection(body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    language = ((cs.m1_topic or {}).get("language", "en")) if cs else "en"
    started = time.perf_counter()
    new_text = rewrite_selection.invoke({
        "chapter_name": chapter_name,
        "language": language,
        "context_before": before,
        "selection": selection,
        "context_after": after,
        # Decision: presets remain safety-bearing base instructions; the
        # student's editable prompt refines them instead of replacing guards
        # that preserve numbers, citations, and non-fabrication behavior.
        "instruction": "\n\n".join(filter(None, [
            _INLINE_INSTRUCTIONS[kind],
            f"Student's additional editing instruction: {body.prompt.strip()}" if body.prompt.strip() else "",
        ])),
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
        metadata=_proposal_metadata(kind, started, {
            "document_fingerprint": _chapter_fingerprint(prose),
            **({"prompt": body.prompt.strip()} if body.prompt.strip() else {}),
        }),
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/{kind}/stream")
def stream_chapter_selection_rewrite(
    project_id: uuid.UUID, chapter_name: str, kind: str, body: RewriteBody,
    user: User = Depends(current_user), db: Session = Depends(db_session),
):
    """Stream a rewrite draft, then persist one reviewable PendingEdit.

    Decision: validation happens before the response starts. Persistence happens
    only after the model iterator completes, so disconnects and model failures
    cannot leave a truncated proposal in the chapter.
    """
    if kind not in _INLINE_INSTRUCTIONS:
        raise HTTPException(404, detail={"error": {"code": "unknown_rewrite_action"}})
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    _validate_document_precondition(prose, body.expected_document_fingerprint)
    _validate_range(prose, body.from_offset, body.to_offset)
    _validate_nonempty_selection(body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    language = ((cs.m1_topic or {}).get("language", "en")) if cs else "en"
    prompt = body.prompt.strip()
    instruction = "\n\n".join(filter(None, [
        _INLINE_INSTRUCTIONS[kind],
        f"Student's additional editing instruction: {prompt}" if prompt else "",
    ]))
    started = time.perf_counter()

    def events():
        parts: list[str] = []
        try:
            for token in stream_rewrite_selection(
                chapter_name=chapter_name, language=language,
                context_before=before, selection=selection,
                context_after=after, instruction=instruction,
            ):
                parts.append(token)
                yield sse_pack({"type": "token", "text": token})
            new_text = "".join(parts).strip()
            if len(new_text) >= 2 and new_text[0] == new_text[-1] and new_text[0] in ('\"', "'"):
                new_text = new_text[1:-1].strip()
            if not new_text:
                raise ValueError("empty rewrite response")
            pe = PendingEdit(
                id=uuid4().hex, chapter_name=chapter_name,
                from_offset=body.from_offset, to_offset=body.to_offset,
                old_text=selection, new_text=new_text, source=kind,
                pending_at=datetime.now(timezone.utc),
                metadata=_proposal_metadata(kind, started, {
                    "document_fingerprint": _chapter_fingerprint(prose),
                    **({"prompt": prompt} if prompt else {}),
                }),
            )
            # FastAPI releases request dependencies before a streaming body is
            # exhausted. Persist with a fresh transaction, and recheck the
            # chapter revision so tokens generated against an older document
            # never become an apparently safe proposal.
            with get_session_factory()() as write_db:
                latest_cs = write_db.get(ContextStore, project_id)
                latest_chapter = _load_chapter_or_404(latest_cs, chapter_name)
                if _chapter_fingerprint(latest_chapter.get("prose", "")) != _chapter_fingerprint(prose):
                    yield sse_pack({
                        "type": "error", "code": "stale_document",
                        "message": "Tài liệu đã thay đổi trong lúc AI xử lý. Hãy chọn lại đoạn văn.",
                    })
                    return
                edit_dict = _append_pending_edit(latest_cs, chapter_name, pe)
                write_db.commit()
            yield sse_pack({"type": "done", "edit": edit_dict})
        except GeneratorExit:
            raise
        except Exception:
            logger.exception("Streaming inline rewrite failed")
            yield sse_pack({"type": "error", "message": "Không thể hoàn tất đề xuất AI. Nội dung chưa được thay đổi."})

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


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
    expected_document_fingerprint: str | None = None


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
    _validate_document_precondition(prose, body.expected_document_fingerprint)
    _validate_range(prose, body.from_offset, body.to_offset)
    _validate_nonempty_selection(body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    started = time.perf_counter()
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
        metadata=_proposal_metadata("translate", started, {
            "target_lang": body.target_lang,
            "document_fingerprint": _chapter_fingerprint(prose),
        }),
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
    expected_document_fingerprint: str | None = None


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
    _validate_document_precondition(prose, body.expected_document_fingerprint)
    if body.at_offset < 0 or body.at_offset > len(prose):
        raise HTTPException(400, detail={"error": {"code": "offset_out_of_range"}})
    pool = _collect_reference_pool(cs)
    matches = [r for r in pool if _reference_id(r) == body.reference_id]
    if not matches:
        raise HTTPException(404, detail={"error": {"code": "reference_not_found"}})
    if len(matches) > 1:
        # Legacy author/year-only records can share an id. Choosing whichever
        # happened to arrive first would cite the wrong paper silently.
        raise HTTPException(409, detail={"error": {"code": "reference_ambiguous"}})
    target = matches[0]
    citation = " " + build_citation_text(target)
    started = time.perf_counter()
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.at_offset,
        to_offset=body.at_offset,
        old_text="",
        new_text=citation,
        source="cite",
        pending_at=datetime.now(timezone.utc),
        metadata=_proposal_metadata("cite", started, {
            "reference_id": body.reference_id,
            "document_fingerprint": _chapter_fingerprint(prose),
        }),
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


class AcceptPendingBody(BaseModel):
    mode: str = "replace"
    expected_document_fingerprint: str | None = None


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/pending/{edit_id}/accept")
def accept_pending_edit(
    project_id: uuid.UUID,
    chapter_name: str,
    edit_id: str,
    body: AcceptPendingBody = AcceptPendingBody(),
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

    actual_fingerprint = _chapter_fingerprint(prose)
    proposal_fingerprint = (target.get("metadata") or {}).get("document_fingerprint")
    from_offset = target["from_offset"]
    to_offset = target["to_offset"]
    fingerprint_changed = bool(
        (proposal_fingerprint and proposal_fingerprint != actual_fingerprint)
        or (not proposal_fingerprint and body.expected_document_fingerprint
            and body.expected_document_fingerprint != actual_fingerprint)
    )
    if fingerprint_changed:
        # Decision: autosave or another accepted edit can shift a still-valid
        # selection. Rebase only on one exact, non-empty anchor. This preserves
        # concurrency safety while avoiding a false stale error for unrelated
        # insertions before the proposal. Empty cite anchors cannot be rebased.
        old_text = target.get("old_text") or ""
        first = prose.find(old_text) if old_text else -1
        unique = first >= 0 and prose.find(old_text, first + 1) == -1
        if not unique:
            raise HTTPException(
                409,
                detail={"error": {"code": "stale_document", "edit_id": edit_id}},
            )
        from_offset, to_offset = first, first + len(old_text)

    # Critical concurrency check: if the prose changed since the edit was created
    # the offsets are stale and splicing would corrupt the document.
    if from_offset > len(prose) or to_offset > len(prose) or prose[from_offset:to_offset] != target["old_text"]:
        raise HTTPException(
            409,
            detail={"error": {"code": "stale_offsets", "edit_id": edit_id}},
        )

    if body.mode not in {"replace", "insert_after"}:
        raise HTTPException(400, detail={"error": {"code": "unknown_accept_mode"}})

    # Offsets validated — now pop and splice. Insert-below keeps the source and
    # adds the proposal after it; this mirrors the editor review menu without
    # weakening the same stale-offset/concurrency guard used by replacement.
    _find_and_pop_edit(ch, edit_id)
    if body.mode == "insert_after":
        insertion = ("\n\n" if to_offset and not prose[:to_offset].endswith("\n") else "") + target["new_text"]
        new_prose = _splice(prose, to_offset, to_offset, insertion)
    else:
        new_prose = _splice(prose, from_offset, to_offset, target["new_text"])
    ch["prose"] = new_prose

    # Re-validate citations so the chapter's used/uncited lists stay current
    pool = _collect_reference_pool(cs)
    validation = validate_citations_plain(new_prose, pool)
    ch["citations_used"] = validation["citations_used"]
    ch["uncited_warnings"] = validation["uncited_warnings"]
    ch["ambiguous_citation_warnings"] = validation["ambiguous_warnings"]

    chapters = (cs.m5_writing or {}).get("chapters") or {}
    _commit_editor_chapters(db, user, project_id, chapters, "Student accepted editor proposal")
    return {**ch, "document_fingerprint": _chapter_fingerprint(new_prose)}


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
    # Passing the store is what makes this the SAME document the chat export
    # produces. Without it run_export builds no cover fields, weaves none of the
    # verified result tables into Chapter 4 and adds no research-model figure to
    # Chapter 3 — the editor was exporting a visibly different thesis.
    artifacts = run_export(sections, str(project_id), references=references, language=language,
                           title=m1.get("research_title"),
                           context_store=nested_slices(cs))

    m5["export_artifacts"] = artifacts
    cs.m5_writing = m5
    flag_modified(cs, "m5_writing")

    # Record the artifacts as `exports` ROWS as well. That table — not
    # m5_writing.export_artifacts — is what the download route authorizes
    # against, and this endpoint was never updated when the source of truth
    # moved: every file the editor's Re-export produced came back
    # `artifact_not_found` on click. Same helper the auto-export hook and the
    # agent's export_docx tool use, so the three cannot drift again.
    for a in artifacts or []:
        s3_key = a.get("s3_key")
        if not s3_key:
            continue
        db.add(Export(
            id=uuid.uuid4(),
            project_id=project_id,
            scope="full",
            kind=a.get("kind") or "docx",
            s3_key=s3_key,
            filename=s3_key.rsplit("/", 1)[-1],
            size_bytes=int(a.get("size_bytes") or 0),
        ))
    db.commit()

    # `missing` lets the UI say "exported 4 of 5 chapters — Conclusion still to
    # draft" instead of implying the doc is complete.
    return {"docx": artifacts[0], "pdf": artifacts[1], "missing_chapters": missing}

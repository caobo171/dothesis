"""Stateless helper tools — no project, no thesis, just text in / answer out.

These exist to be exposed through the MCP connector (mcp/server_lite.py), where
the useful shape is a single self-contained call a student can make mid-chat.
Everything project-scoped is already served by chat.py / papers.py; this module
is only for the things that need nothing but their arguments.

Both endpoints are also plain REST, so the web app can use them without going
near MCP.
"""
from __future__ import annotations

import io
import logging
import re

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user, stream_user_factory
from ..jwt_auth import AuthedBody
from ..models import User
from ..tool_billing import Timer, record_tool_run, surface_of
from ..user_memory import load_user_prefs, write_user_prefs
from .uploads import s3_from_env

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools", tags=["tools"])


# ---------------------------------------------------------------------------
# Writing rhythm
# ---------------------------------------------------------------------------

class RhythmBody(BaseModel):
    # Plain BaseModel, NOT AuthedBody — same as HumanizeIn, and for the same
    # reason: these are called over MCP, where the token rides in the
    # Authorization header and there is no `access_token` in the body. An
    # AuthedBody here makes Pydantic reject every connector call with a 422
    # before `current_user` ever gets to read the header. The web client's
    # apiFetch still injects access_token into the body and `_extract_token`
    # still finds it there, so both transports work.
    text: str = Field(min_length=1, max_length=40000)


class RhythmOut(BaseModel):
    ok: bool
    score: float | None = None
    verdict: str
    basis: str
    detail: str | None = None
    credits_charged: int = 0


@router.post("/writing-rhythm", response_model=RhythmOut)
def writing_rhythm(request: Request, body: RhythmBody,
                   user: User = Depends(current_user),
                   db: Session = Depends(db_session)) -> RhythmOut:
    """Score how MECHANICAL the sentence rhythm of a passage is, 0-1.

    NOT an AI detector, and named so it cannot be mistaken for one. It runs the
    `StylometricScorer` that drives the humanize loop, whose own docstring is
    explicit that it is "a WEAK signal ... must not be read as a verdict": it
    measures burstiness (variance in sentence length) and formulaic-connector
    density, and it cannot see perplexity, which is half of what real detectors
    use. Correlation with Turnitin/GPTZero is not claimed and should not be
    implied anywhere this is surfaced.

    What it IS good for, and why it's worth exposing: human academic prose
    alternates short and long sentences; LLM drafts land on a metronome. A high
    score is a concrete, explainable writing note — "your sentences are all the
    same length" — that a student can act on. That is useful advice whether or
    not any detector agrees.
    """
    from orchestrator.tools.detector import StylometricScorer  # noqa: PLC0415

    with Timer() as t:
        score = StylometricScorer().score(body.text)
    if score is None:
        # Too short to judge is not a run: nothing was scored, so nothing is
        # billed, but the attempt is still recorded — "how often does this
        # bounce people?" is worth being able to answer.
        record_tool_run(db, user, surface=surface_of(request), tool="writing-rhythm", ok=False,
                        error="too_short", duration_ms=t.ms)
        return RhythmOut(
            ok=False, verdict="too_short", basis="sentence-length burstiness",
            detail="Needs at least 3 sentences to judge rhythm.")

    charge = record_tool_run(db, user, surface=surface_of(request), tool="writing-rhythm", duration_ms=t.ms)

    if score >= 0.7:
        verdict = "very_even"
    elif score >= 0.45:
        verdict = "somewhat_even"
    else:
        verdict = "varied"
    return RhythmOut(
        ok=True, score=score, verdict=verdict,
        credits_charged=charge.charged,
        basis="sentence-length burstiness + formulaic connector density",
        detail={
            "very_even": "Sentences are close to uniform length — the pattern LLM "
                         "drafts fall into. Vary them: break one long sentence, "
                         "merge two short ones.",
            "somewhat_even": "Some rhythm, but still fairly regular.",
            "varied": "Sentence lengths vary the way human academic prose does.",
        }[verdict])


# ---------------------------------------------------------------------------
# Citation verification
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.I)


class CitationBody(BaseModel):
    # Plain BaseModel for the header-auth reason in RhythmBody above.
    # One free-text field on purpose. A student pastes whatever their reference
    # manager gave them — a DOI, a URL, or a full formatted reference — and
    # should not have to work out which box it belongs in.
    reference: str = Field(min_length=3, max_length=2000)


class CitationOut(BaseModel):
    ok: bool
    found: bool
    doi: str | None = None
    title: str | None = None
    authors: str | None = None
    year: int | None = None
    container: str | None = None
    url: str | None = None
    matched_by: str | None = None
    warning: str | None = None
    detail: str | None = None
    # Charged per RUN, so this is 0 on the per-item rows inside a list check —
    # the list's own total is on CitationListOut.
    credits_charged: int = 0


# Thin wrappers over orchestrator.tools.crossref, which is where the HTTP calls
# now live so the .docx citer can share them. Kept as module-level functions
# rather than direct imports because every test in test_tools_router monkeypatches
# these names, and because the indirection is what lets them.
def _crossref_by_doi(doi: str) -> dict | None:
    from orchestrator.tools.crossref import by_doi  # noqa: PLC0415
    return by_doi(doi)


def _crossref_by_text(text: str) -> dict | None:
    from orchestrator.tools.crossref import by_text  # noqa: PLC0415
    return by_text(text)


def _fmt(msg: dict, matched_by: str) -> CitationOut:
    authors = ", ".join(
        f"{a.get('family', '')}{', ' + a.get('given', '') if a.get('given') else ''}".strip(", ")
        for a in (msg.get("author") or [])[:5]) or None
    parts = (msg.get("issued") or {}).get("date-parts") or [[]]
    year = parts[0][0] if parts and parts[0] else None
    title = (msg.get("title") or [None])[0]
    return CitationOut(
        ok=True, found=True, doi=msg.get("DOI"), title=title, authors=authors,
        year=year if isinstance(year, int) else None,
        container=(msg.get("container-title") or [None])[0],
        url=msg.get("URL"), matched_by=matched_by)


def _verify_one(ref: str) -> CitationOut:
    """The whole single-reference decision, shared by both endpoints.

    Extracted so the batch route cannot drift into a second, more optimistic
    reading of the same CrossRef response — the honesty rules below (fuzzy is
    not proof, unreachable is not fake) have to hold identically whether a
    student checks one reference or fifty.
    """
    ref = ref.strip()
    doi_match = _DOI_RE.search(ref)
    try:
        if doi_match:
            msg = _crossref_by_doi(doi_match.group(1))
            if msg:
                return _fmt(msg, "doi")
            return CitationOut(
                ok=True, found=False, matched_by="doi",
                detail="CrossRef has no record of that DOI. Check it character by "
                       "character before assuming the source is fabricated — a "
                       "typo looks identical to an invention here.")
        msg = _crossref_by_text(ref)
        if not msg:
            return CitationOut(
                ok=True, found=False, matched_by="search",
                detail="No close match in CrossRef. That is not proof it is fake: "
                       "books, theses and many regional journals are not indexed "
                       "there. Verify by hand before dropping it.")
        out = _fmt(msg, "search")
        out.warning = ("Fuzzy match — CrossRef returns a best guess for any query. "
                       "Compare the title, authors and year below against your "
                       "reference before trusting it.")
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("verify-citation lookup failed: %s", e)
        return CitationOut(
            ok=False, found=False,
            detail=f"Could not reach CrossRef ({type(e).__name__}). "
                   "No conclusion about this reference — try again shortly.")


@router.post("/verify-citation", response_model=CitationOut)
def verify_citation(request: Request, body: CitationBody,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)) -> CitationOut:
    """Check ONE reference against CrossRef — does this actually exist?

    The single most common way an LLM-assisted thesis fails: a reference that
    reads perfectly and does not exist. A DOI is an exact lookup and the answer
    is definitive. Without one we fall back to a bibliographic search, which is
    FUZZY — CrossRef returns its best match for any query, so a hit is evidence
    that something similar exists, not proof that this reference is real. That
    distinction is carried in the response (`matched_by`, `warning`) rather than
    flattened into a boolean, because "probably fine" and "confirmed" are very
    different things to a student about to submit.

    A network failure returns ok=false, never found=false. Reporting an
    unreachable API as "this citation is fake" would be the worst possible
    error: it invites a student to delete a real source.

    For a whole reference list, use /tools/verify-citations (plural). Pasting a
    document here cannot work: `_crossref_by_text` sends only the first 400
    characters, so a chapter would be matched on its opening sentence and come
    back "probably fine" against an unrelated paper.
    """
    with Timer() as t:
        out = _verify_one(body.reference)
    # One lookup, one unit. `ok=False` here means CrossRef was unreachable —
    # our failure, so it bills nothing.
    charge = record_tool_run(db, user, surface=surface_of(request), tool="verify-citation", ok=out.ok,
                             error=None if out.ok else "unreachable",
                             units=1, duration_ms=t.ms)
    out.credits_charged = charge.charged
    return out


# ---------------------------------------------------------------------------
# Citation verification — whole reference list
# ---------------------------------------------------------------------------

# Where a Vietnamese or English thesis starts listing its sources. Matched
# case-insensitively; the LAST hit wins because the same words appear earlier in
# the table of contents, and cutting at the first one would hand us the TOC.
_REF_HEADINGS = re.compile(
    r"^\s*(?:danh\s+m[ụu]c\s+)?(?:t[àa]i\s+li[ệe]u\s+tham\s+kh[ảa]o"
    r"|references?|bibliography|works\s+cited)\s*:?\s*$",
    re.I | re.M,
)

# A 4-digit year, 1800-2099. Every citation style puts one somewhere, so this is
# the cheapest way to tell a reference apart from a body paragraph.
_YEAR_RE = re.compile(r"\b(?:1[89]|20)\d{2}\b")

# "[12] ", "12. ", "12) " — numbered reference lists, which is how most
# Vietnamese theses format theirs.
_NUMBERED_RE = re.compile(r"^\s*\[?\d{1,3}[\].)]\s+")

# Ceiling on one request. CrossRef is a free public API and this endpoint costs
# the student nothing, so the limit is politeness to CrossRef rather than to us:
# 50 lookups is already ~10 seconds of someone else's capacity.
_MAX_REFS = 50

# A reference shorter than this is a fragment; longer than this is a paragraph
# that happens to contain a year.
_REF_MIN_CHARS = 20
_REF_MAX_CHARS = 600

# How many wrapped lines may be glued together before we give up on a candidate.
# PDF extraction breaks one reference across 2-4 lines; a runaway merge would
# swallow the paragraphs after it.
_MAX_CONTINUATION_LINES = 4


def _looks_complete(candidate: str) -> bool:
    """Does this candidate already carry the year/DOI that ends a reference?"""
    return bool(_YEAR_RE.search(candidate) or _DOI_RE.search(candidate))


def extract_references(text: str) -> list[str]:
    """Pull the individual references out of a pasted document.

    Deliberately conservative: a line is only offered for checking if it carries
    a year or a DOI. Reporting "not found in CrossRef" for a heading or a stray
    sentence would teach students to ignore this tool's warnings, which are the
    entire point of it.

    Returns them in document order, de-duplicated, uncapped — the caller decides
    how many to actually look up.
    """
    body = text.replace("\r\n", "\n")

    # Start at the reference list when the document has one. Everything before
    # it is prose, and prose lines with a year in them ("in 2019, Nguyen showed
    # that...") would otherwise be checked as if they were citations.
    headings = list(_REF_HEADINGS.finditer(body))
    if headings:
        body = body[headings[-1].end():]

    out: list[str] = []
    seen: set[str] = set()
    buf = ""
    glued = 0

    def flush() -> None:
        nonlocal buf, glued
        cand = " ".join(buf.split())
        buf = ""
        glued = 0
        cand = _NUMBERED_RE.sub("", cand).strip()
        if not (_REF_MIN_CHARS <= len(cand) <= _REF_MAX_CHARS):
            return
        if not _looks_complete(cand):
            return
        key = cand.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(cand)

    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        # A numbered marker always starts a new entry, even mid-merge — it is
        # the one unambiguous signal a reference list gives us.
        starts_entry = bool(_NUMBERED_RE.match(line))
        if buf and not starts_entry and not _looks_complete(buf) and glued < _MAX_CONTINUATION_LINES:
            buf = f"{buf} {line}"
            glued += 1
            continue
        flush()
        buf = line
    flush()
    return out


class CitationListBody(BaseModel):
    # Plain BaseModel for the header-auth reason in RhythmBody above.
    #
    # 400k characters, NOT the 40k the other text endpoints use. Those take a
    # passage; this one is explicitly fed a whole thesis by the attach control,
    # and a 100-page Vietnamese thesis extracts to 150-250k characters — 40k
    # rejected the exact input the mode exists to accept, which is how it was
    # found. Nothing is sent to a model here (no token cost); the text is only
    # scanned for reference lines, so the ceiling is about request size.
    text: str = Field(min_length=3, max_length=400000)


class CitationItem(CitationOut):
    """One verdict, plus the reference line it came from.

    The line is echoed back because the student never typed these individually —
    they attached a document — so a result with no reference attached to it
    would be unattributable.
    """
    reference: str


class CitationListOut(BaseModel):
    ok: bool
    # Candidates found in the document vs. how many were actually looked up.
    # Kept separate so a truncated run says so instead of quietly reporting on
    # the first 50 as if they were the whole list.
    detected: int = 0
    checked: int = 0
    truncated: bool = False
    items: list[CitationItem] = []
    detail: str | None = None
    credits_charged: int = 0


@router.post("/verify-citations", response_model=CitationListOut)
def verify_citations(
    request: Request, body: CitationListBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> CitationListOut:
    """Check every reference in a pasted document or reference list.

    This is the flow students actually have: they finish a thesis, then want to
    know which of its sources are real — one at a time is not a review, it is an
    afternoon. The per-reference verdicts are produced by the exact same
    `_verify_one` the single endpoint uses, so nothing here is more confident
    than the single check would have been.

    Lookups run concurrently but only a few at a time: CrossRef is free and
    public, and a 50-way fan-out from every student would be a good way to lose
    access to it for everyone.
    """
    refs = extract_references(body.text)
    if not refs:
        # Nothing was looked up, so nothing is billed. Still recorded: "students
        # paste something we cannot find references in" is a product problem,
        # and it is invisible unless the attempt leaves a row.
        record_tool_run(db, user, surface=surface_of(request), tool="verify-citations", ok=False,
                        error="no_references_found")
        return CitationListOut(
            ok=True, detected=0, checked=0,
            detail="No references found. This looks for lines carrying a year or "
                   "a DOI, usually under a 'Tài liệu tham khảo' / 'References' "
                   "heading — paste the reference list, or the whole document.")

    capped = refs[:_MAX_REFS]
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    with Timer() as t, ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_verify_one, capped))

    items = [
        CitationItem(reference=ref, **res.model_dump())
        for ref, res in zip(capped, results, strict=True)
    ]
    # Billed per reference ACTUALLY looked up, not per reference detected: a
    # truncated run charges for the 50 it checked, never for the 200 it found.
    # References CrossRef could not be reached for are excluded for the same
    # reason the single check bills nothing on a transport failure.
    reached = sum(1 for r in results if r.ok)
    # A run where CrossRef answered nothing at all is a FAILED run, not a
    # successful one that happened to check zero references — otherwise an
    # outage looks like normal traffic in the admin view.
    charge = record_tool_run(db, user, surface=surface_of(request), tool="verify-citations",
                             ok=reached > 0,
                             error=None if reached else "crossref_unreachable",
                             units=reached, duration_ms=t.ms)
    return CitationListOut(
        ok=True, detected=len(refs), checked=len(items),
        truncated=len(refs) > len(capped), items=items,
        credits_charged=charge.charged)


# ---------------------------------------------------------------------------
# Similarity ("plagiarism") check
# ---------------------------------------------------------------------------

class SimilarityBody(BaseModel):
    # Plain BaseModel for the same MCP/web dual-transport reason as RhythmBody.
    text: str = Field(min_length=1, max_length=40000)
    language: str = "vi"


class SimilarityMatch(BaseModel):
    source: str
    url: str | None = None
    overlap: float
    excerpt: str | None = None


class SimilarityOut(BaseModel):
    ok: bool
    # None whenever we did not actually check. A 0.0 here would read as "no
    # overlap found", which is the one wrong answer this endpoint must never
    # give — a student would take it as a clean bill of health.
    score: float | None = None
    matches: list[SimilarityMatch] = []
    provider: str | None = None
    error: str | None = None
    detail: str | None = None
    credits_charged: int = 0


@router.post("/plagiarism-check", response_model=SimilarityOut)
def plagiarism_check(request: Request, body: SimilarityBody,
                     user: User = Depends(current_user),
                     db: Session = Depends(db_session)) -> SimilarityOut:
    """Check a passage against a similarity provider, if one is configured.

    There is no local fallback and there must never be one. A similarity check
    needs a corpus — the web, a paper index, the institution's own submissions —
    and we have none of them. An LLM asked "is this plagiarised?" will produce a
    confident number derived from nothing, and a student who reads that number
    as a Turnitin proxy submits on the strength of it.

    So an unconfigured deployment returns ok=false / provider_not_configured,
    and `score` stays None rather than 0.0. See orchestrator/tools/plagiarism.py
    for how to wire a vendor.
    """
    from orchestrator.tools.plagiarism import get_provider  # noqa: PLC0415

    provider = get_provider()
    if provider is None:
        # Not billed, on purpose: nothing was checked. Charging for a check the
        # deployment cannot perform is the clearest possible way to lose a
        # customer's trust in the meter.
        record_tool_run(db, user, surface=surface_of(request), tool="plagiarism-check", ok=False,
                        error="provider_not_configured")
        return SimilarityOut(
            ok=False,
            error="provider_not_configured",
            detail="No similarity provider is configured for this deployment, "
                   "so this passage was NOT checked. This is not a result of "
                   "'no matches found'.",
        )
    try:
        with Timer() as t:
            raw = provider.check(body.text, language=body.language)
    except Exception:  # noqa: BLE001
        logger.exception("plagiarism-check failed for user %s", user.id)
        record_tool_run(db, user, surface=surface_of(request), tool="plagiarism-check", ok=False,
                        error="provider_error", duration_ms=t.ms)
        # Never degrade a transport failure into "clean" — same rule as
        # verify_citation's network-failure branch.
        return SimilarityOut(
            ok=False, error="provider_error",
            detail="The similarity provider could not be reached, so this "
                   "passage was NOT checked.",
        )
    charge = record_tool_run(db, user, surface=surface_of(request), tool="plagiarism-check", duration_ms=t.ms)
    return SimilarityOut(
        ok=True,
        score=raw.get("score"),
        matches=[SimilarityMatch(**m) for m in (raw.get("matches") or [])],
        provider=raw.get("provider") or getattr(provider, "name", None),
        credits_charged=charge.charged,
    )


# ---------------------------------------------------------------------------
# Text extraction — file in, plain text out
# ---------------------------------------------------------------------------

class ExtractOut(BaseModel):
    ok: bool
    text: str = ""
    chars: int = 0
    page_count: int = 0
    filename: str | None = None
    error: str | None = None
    detail: str | None = None


@router.post("/extract-text", response_model=ExtractOut)
async def extract_text(request: Request, file: UploadFile = File(...),
                       user: User = Depends(current_user),
                       db: Session = Depends(db_session)) -> ExtractOut:
    """Pull plain text out of a PDF / .docx / .txt. Nothing is stored.

    The existing upload route (uploads.upload_paper) is project-scoped and puts
    the bytes in S3 with a PaperUpload row, because those files ARE the thesis
    and get read again later. A tool call is the opposite: the file is a
    transport for one passage, so persisting it would create an S3 object and a
    DB row nobody ever reads, attached to a project the student does not have.

    Deliberately reuses uploads' allowlist, size cap and extractors rather than
    restating them — a second copy of "which types can we read" is how the two
    surfaces end up disagreeing about .docx.
    """
    from .uploads import (  # noqa: PLC0415 — shares the allowlist, cap, extractors
        _ALLOWED_EXT, _ALLOWED_MIME, _DOCX_MIME, _extract_docx_text, _max_bytes,
    )
    from ..pdf_extract import extract_pdf_text  # noqa: PLC0415

    mime = file.content_type or "application/octet-stream"
    fname = (file.filename or "").lower()
    if mime not in _ALLOWED_MIME and not fname.endswith(_ALLOWED_EXT):
        raise HTTPException(415, detail={"error": {
            "code": "bad_mime",
            "message": f"unsupported file type: {mime or fname}"}})

    body = await file.read()
    if len(body) > _max_bytes():
        raise HTTPException(413, detail={"error": {
            "code": "too_large",
            "message": f"file exceeds {_max_bytes()} bytes"}})

    page_count = 0
    if mime == "application/pdf" or fname.endswith(".pdf"):
        text, page_count = extract_pdf_text(body)
    elif mime == _DOCX_MIME or fname.endswith(".docx"):
        text, page_count = _extract_docx_text(body)
    else:
        text = body.decode("utf-8", errors="replace")

    text = (text or "").strip()
    # Free (pricing.TOOL_FREE) but recorded: this is the INPUT step for the paid
    # tools, so billing it charges a student twice for one file — while "how
    # many people upload a document and never run anything on it" is a funnel
    # number that only exists if the attempt leaves a row.
    if not text:
        record_tool_run(db, user, surface=surface_of(request), tool="extract-text", ok=False, error="no_text")
        # A scanned PDF is images, not text. Say which problem it is — "no text"
        # sends the student looking for a bug in our parser instead of exporting
        # a text-based copy.
        return ExtractOut(
            ok=False, filename=file.filename, error="no_text",
            detail="No text could be read from this file. If it's a scan or "
                   "photo, the pages are images — export a text-based PDF or "
                   "paste the passage instead.")
    record_tool_run(db, user, surface=surface_of(request), tool="extract-text")
    return ExtractOut(ok=True, text=text, chars=len(text),
                      page_count=page_count, filename=file.filename)


# ---------------------------------------------------------------------------
# Writing anchor — save once, reuse everywhere
# ---------------------------------------------------------------------------

class AnchorIn(BaseModel):
    # Plain BaseModel for the header-auth reason in RhythmBody above.
    anchor: str = Field(min_length=1, max_length=20000)


class AnchorOut(BaseModel):
    ok: bool
    has_anchor: bool = False
    words: int = 0
    preview: str | None = None
    error: str | None = None
    detail: str | None = None


def _anchor_words(s: str) -> int:
    return len((s or "").split())


@router.post("/writing-anchor/save", response_model=AnchorOut)
def save_writing_anchor(body: AnchorIn, user: User = Depends(current_user),
                        db: Session = Depends(db_session)) -> AnchorOut:
    """Store the caller's style anchor. No LLM, no credits.

    Until now the anchor was only ever persisted as a SIDE EFFECT of a
    successful humanize (routers/humanize.py saves it when the rewrite returns
    ok). That made the precondition cost money: to save the sample the feature
    refuses to run without, you first had to pay for a rewrite — and if that
    rewrite failed verification, your sample was discarded with it.

    Saving is its own action now. The rewrite path still saves on success, so
    nothing regresses for callers that never visit this route.
    """
    anchor = body.anchor.strip()
    words = _anchor_words(anchor)
    if words < 50:
        # Not a hard technical limit — the pass will run — but an anchor this
        # short has no rhythm to copy, which is the whole mechanism. Refusing
        # beats silently pinning the user to a sample that cannot work.
        return AnchorOut(
            ok=False, words=words, error="too_short",
            detail=f"{words} words isn't enough rhythm to copy. Aim for ~150 "
                   "words of your own writing.")
    try:
        write_user_prefs(db, user.id, {"writing_anchor": anchor})
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("writing-anchor: save failed for user %s", user.id)
        db.rollback()
        return AnchorOut(ok=False, error="save_failed",
                         detail="Could not save your writing sample. Try again.")
    return AnchorOut(ok=True, has_anchor=True, words=words,
                     preview=anchor[:160])


@router.post("/writing-anchor", response_model=AnchorOut)
def get_writing_anchor(_body: AuthedBody, user: User = Depends(current_user),
                       db: Session = Depends(db_session)) -> AnchorOut:
    """Whether this user already has an anchor saved, and a preview of it.

    Lets the humanize UI say "using your saved sample" instead of demanding
    ~150 words from someone who supplied them weeks ago.
    """
    anchor = ((load_user_prefs(db, user.id) or {}).get("writing_anchor") or "").strip()
    if not anchor:
        return AnchorOut(ok=True, has_anchor=False)
    return AnchorOut(ok=True, has_anchor=True, words=_anchor_words(anchor),
                     preview=anchor[:160])


# ---------------------------------------------------------------------------
# My tool runs — the caller's own history
# ---------------------------------------------------------------------------

class MyRunsBody(AuthedBody):
    page: int = 1
    page_size: int = 20


class MyRun(BaseModel):
    id: str
    tool: str
    ok: bool
    error: str | None = None
    units: int = 0
    credits_charged: int = 0
    # What it SHOULD have cost. Shown only when it differs — a student whose
    # balance ran out mid-document is entitled to know the run was worth more
    # than it took, rather than discovering the shortfall as a surprise later.
    credits_cost: int = 0
    created_at: str
    # Booleans, not URIs: the client needs to know a file is THERE, and has no
    # business seeing the S3 key it lives at.
    has_input: bool = False
    has_output: bool = False
    files_expire_at: str | None = None
    # What the run did — {"rewritten": 80, "skipped": 52}. The response headers
    # carried these and the history dropped them, so a run that left half the
    # document untouched looked identical to a clean one.
    metrics: dict | None = None
    parent_run_id: str | None = None
    status: str = "done"
    progress_done: int = 0
    progress_total: int = 0


class MyRunsOut(BaseModel):
    items: list[MyRun] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


@router.post("/runs", response_model=MyRunsOut)
def my_tool_runs(body: MyRunsBody, user: User = Depends(current_user),
                 db: Session = Depends(db_session)) -> MyRunsOut:
    """The caller's own tool history — what they ran and what it cost them.

    /transactions already lists the DEBITS, but that is not the same list and it
    is the wrong shape for this question. A run that charged nothing writes no
    credit transaction at all: the free tools, a failed run, and — the one that
    matters — a run whose cost the balance could not cover. Those are exactly
    the rows a student needs when they ask why their credits moved, or why they
    did not.

    Scoped to `user.id` with no override. The admin view is a separate router
    behind require_admin; a filter parameter here is how one becomes the other
    by accident.
    """
    from ..models import ToolRun  # noqa: PLC0415

    page = max(1, body.page)
    size = min(max(1, body.page_size), 100)
    where = ToolRun.user_id == user.id
    total = db.scalar(
        select(func.count()).select_from(ToolRun).where(where)) or 0
    rows = db.scalars(
        select(ToolRun).where(where)
        .order_by(ToolRun.created_at.desc(), ToolRun.id.desc())
        .offset((page - 1) * size).limit(size)
    ).all()
    return MyRunsOut(
        items=[MyRun(
            id=str(r.id), tool=r.tool, ok=r.ok, error=r.error, units=r.units,
            credits_charged=r.credits_charged, credits_cost=r.credits_cost,
            created_at=r.created_at.isoformat(),
            has_input=bool(r.input_s3_uri), has_output=bool(r.output_s3_uri),
            files_expire_at=(r.files_expire_at.isoformat()
                             if r.files_expire_at else None),
            metrics=r.metrics, status=r.status,
            parent_run_id=(str(r.parent_run_id) if r.parent_run_id else None),
            progress_done=r.progress_done, progress_total=r.progress_total,
        ) for r in rows],
        total=total, page=page, page_size=size)


class RunIdBody(AuthedBody):
    """Nothing but the token — the run is in the path. Still a POST body,
    because that is where the token rides (CLAUDE.md)."""


class RunProgressOut(BaseModel):
    status: str
    done: int = 0
    total: int = 0


class ActiveRunOut(BaseModel):
    id: str | None = None
    tool: str | None = None
    done: int = 0
    total: int = 0


# Comfortably past the longest job that opens a run row — the citation search's
# own ceiling is 900s + a 60s watchdog. Anything older is a row whose process
# died without reaching its finally.
_ACTIVE_RUN_MAX_AGE_S = 3600


@router.post("/runs/active", response_model=ActiveRunOut)
def active_run(body: AuthedBody, user: User = Depends(current_user),
               db: Session = Depends(db_session)) -> ActiveRunOut:
    """The caller's run that is still going, if any.

    Exists because of a chicken-and-egg: the page that most needs to show
    progress is the one holding the POST open, and it cannot know the run id
    until that POST returns — which is the very thing it is waiting for. So the
    client asks "what am I running right now" instead of "how is run 42 doing".

    Scoped to the caller and to the newest running row. Two concurrent document
    runs from one person would report the later one; that is a strictly better
    answer than the spinner with no number that this replaces.
    """
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from ..models import ToolRun  # noqa: PLC0415

    # Ignore rows older than the longest job anyone runs. A row only leaves
    # `running` in its own process's finally block, so a job that hangs or is
    # killed leaves one behind for good — and this endpoint would then hand the
    # next screen the user opened a spinner for work that ended hours ago.
    # Measured: a citation search stuck at step 1 of 3 was still the "active
    # run" long after the student had moved on.
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_ACTIVE_RUN_MAX_AGE_S)
    row = db.scalars(
        select(ToolRun)
        .where(ToolRun.user_id == user.id, ToolRun.status == "running",
               ToolRun.created_at >= cutoff)
        .order_by(ToolRun.id.desc()).limit(1)
    ).first()
    if row is None:
        return ActiveRunOut()
    return ActiveRunOut(id=str(row.id), tool=row.tool,
                        done=row.progress_done, total=row.progress_total)


@router.post("/runs/{run_id}/progress", response_model=RunProgressOut)
def run_progress(run_id: int, body: RunIdBody,
                 user: User = Depends(current_user),
                 db: Session = Depends(db_session)) -> RunProgressOut:
    """How far along a run is, while it is still running.

    Polled rather than streamed: a document walk is minutes long, so a 2-second
    poll costs nothing next to it, and SSE would need a second transport for a
    number that changes ~70 times in total.

    A read, so it takes `readable_run` — an admin watching a student's run is
    the same access as opening it afterwards.
    """
    from ..auth_admin import readable_run  # noqa: PLC0415

    run = readable_run(db, user, run_id)
    return RunProgressOut(status=run.status, done=run.progress_done,
                          total=run.progress_total)


class DiffSegmentOut(BaseModel):
    op: str
    text: str


class DiffParagraphOut(BaseModel):
    index: int
    before: str
    after: str
    segments: list[DiffSegmentOut] = []


class RunDiffOut(BaseModel):
    ok: bool = True
    aligned: bool = True
    tool: str = ""
    filename: str | None = None
    total: int = 0
    changed: int = 0
    unchanged: int = 0
    truncated: bool = False
    items: list[DiffParagraphOut] = []


class RunDiffIn(AuthedBody):
    # Unchanged paragraphs are the bulk of a thesis and the client renders them
    # from nothing, so they are opt-in rather than shipped by default.
    changed_only: bool = True
    limit: int = 200


@router.post("/runs/{run_id}/diff", response_model=RunDiffOut)
async def run_diff(run_id: int, body: RunDiffIn,
                   user: User = Depends(current_user),
                   db: Session = Depends(db_session)) -> RunDiffOut:
    """Paragraph-by-paragraph diff of a run's stored input against its output.

    A read, so it takes the same owner-or-journaled-admin gate as the download.
    Both files are already kept for 30 days; this derives the comparison from
    them rather than storing a third artifact.
    """
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415
    from orchestrator.tools.docx_diff import diff_docx  # noqa: PLC0415
    from ..auth_admin import readable_run  # noqa: PLC0415

    run = readable_run(db, user, run_id)
    before, after = await _run_diff_files(run, run_id)

    d = await run_in_threadpool(
        diff_docx, before, after,
        limit=max(1, min(body.limit, 500)), changed_only=body.changed_only)
    return RunDiffOut(
        aligned=d.aligned, tool=run.tool, filename=run.input_filename,
        total=d.total, changed=d.changed, unchanged=d.unchanged,
        truncated=d.truncated,
        items=[DiffParagraphOut(
            index=i.index, before=i.before, after=i.after,
            segments=[DiffSegmentOut(op=s.op, text=s.text) for s in i.segments],
        ) for i in d.items],
    )


async def _run_diff_files(run, run_id: int) -> tuple[bytes, bytes]:
    """Both stored halves of a run, or 410. Shared by the JSON and file views."""
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415
    from ..tool_artifacts import FILE_RETENTION_DAYS, uri_parts  # noqa: PLC0415

    if not (run.input_s3_uri and run.output_s3_uri):
        raise HTTPException(410, detail={"error": {
            "code": "file_expired",
            "message": f"Both files are needed to show what changed, and they "
                       f"are kept for {FILE_RETENTION_DAYS} days."}})

    def _fetch() -> tuple[bytes, bytes]:
        s3 = s3_from_env()
        got = []
        for uri in (run.input_s3_uri, run.output_s3_uri):
            bucket, key = uri_parts(uri)
            got.append(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        return got[0], got[1]

    try:
        return await run_in_threadpool(_fetch)
    except Exception:  # noqa: BLE001
        logger.exception("run diff: could not read stored files for run %s", run_id)
        raise HTTPException(410, detail={"error": {
            "code": "file_expired", "message": "The stored files could not be read."}})


@router.get("/runs/{run_id}/diff.{fmt}")
async def download_run_diff(
    run_id: int, fmt: str,
    # GET-only (browser <a download>), ?st= scoped to this run's diff.
    user: User = Depends(stream_user_factory(
        lambda run_id, fmt: f"tool-run-diff:{run_id}")),
    db: Session = Depends(db_session),
):
    """The diff as a self-contained .html or .pdf, for reading somewhere else.

    Exists because the on-screen view cannot leave the app: a supervisor, a
    second opinion, or a bug report needs a file. HTML is the one that travels —
    searchable, greppable, diffable — and the PDF is for handing to someone.
    """
    from fastapi.responses import Response  # noqa: PLC0415
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415
    from orchestrator.tools.docx_diff import (  # noqa: PLC0415
        diff_docx, html_to_pdf, render_diff_html)
    from ..auth_admin import readable_run  # noqa: PLC0415

    if fmt not in ("html", "pdf"):
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    run = readable_run(db, user, run_id)
    before, after = await _run_diff_files(run, run_id)

    # Everything, not just the changed paragraphs: the file is for reading away
    # from the app, where "show unchanged" is not a checkbox you can tick.
    d = await run_in_threadpool(diff_docx, before, after,
                                limit=5000, changed_only=False)
    name = (run.input_filename or "document.docx").rsplit(".", 1)[0]
    html = render_diff_html(
        d, title=name,
        meta=f"{d.changed} changed · {d.unchanged} unchanged · {d.total} paragraphs")

    if fmt == "html":
        return Response(
            content=html.encode("utf-8"), media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}-diff.html"'})

    pdf = await run_in_threadpool(html_to_pdf, html)
    if pdf is None:
        # LibreOffice absent or hung. Say which format still works rather than
        # failing blank — the HTML carries the same content.
        raise HTTPException(503, detail={"error": {
            "code": "pdf_unavailable",
            "message": "PDF conversion is unavailable on this server. "
                       "Download the HTML version instead."}})
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}-diff.pdf"'})


@router.post("/runs/{run_id}/files/delete")
def delete_run_files(run_id: int, body: RunIdBody,
                     user: User = Depends(current_user),
                     db: Session = Depends(db_session)) -> dict:
    """Delete a run's stored files now, without waiting for the 30 days.

    Owner-only: this destroys data, and an admin who may READ a student's run
    must not be able to remove it. Nulls the URIs and keeps the row, exactly as
    the scheduled purge does — the run is a billing record either way.

    Idempotent: deleting the files of a run that has none is a no-op, not a 404,
    because the student's intent ("make sure it is gone") is already satisfied.
    """
    from ..auth_admin import owned_run  # noqa: PLC0415
    from ..tool_artifacts import uri_parts  # noqa: PLC0415

    run = owned_run(db, user, run_id)
    uris = [u for u in (run.input_s3_uri, run.output_s3_uri) if u]
    if uris:
        s3 = s3_from_env()
        for uri in uris:
            bucket, key = uri_parts(uri)
            if not (bucket and key):
                continue
            try:
                s3.delete_object(Bucket=bucket, Key=key)
            except Exception:  # noqa: BLE001
                # Logged, and the row is NOT cleared — the nightly purge will
                # find it again. Clearing it here would orphan the object with
                # nothing left pointing at it to retry.
                logger.exception("delete_run_files: S3 delete failed for run %s", run_id)
                raise HTTPException(502, detail={"error": {
                    "code": "delete_failed",
                    "message": "The files could not be deleted. Try again shortly."}})
        run.input_s3_uri = None
        run.output_s3_uri = None
        db.commit()
    return {"ok": True, "deleted": len(uris)}


@router.post("/runs/{run_id}/rerun")
async def rerun_tool_run(run_id: int, body: RunIdBody, request: Request,
                         user: User = Depends(current_user),
                         db: Session = Depends(db_session)):
    """Run a document tool again on the input it was given the first time.

    Owner-only: this spends credits and appends to their history. Charged like
    any other run, because it IS one — the model work is done again in full.
    """
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415
    from ..auth_admin import owned_run  # noqa: PLC0415
    from ..tool_artifacts import (  # noqa: PLC0415
        FILE_RETENTION_DAYS, store_run_files, uri_parts)
    from ..tool_billing import begin_tool_run, bump_progress  # noqa: PLC0415
    from ..user_memory import load_user_prefs as _prefs  # noqa: PLC0415
    from .uploads import _DOCX_MIME  # noqa: PLC0415

    run = owned_run(db, user, run_id)
    if run.tool not in ("humanize-docx", "cite-docx"):
        raise HTTPException(422, detail={"error": {
            "code": "not_rerunnable",
            "message": "Only whole-document tools can be run again."}})
    if not run.input_s3_uri:
        raise HTTPException(410, detail={"error": {
            "code": "file_expired",
            "message": f"The original file is no longer stored — inputs are "
                       f"kept for {FILE_RETENTION_DAYS} days."}})

    bucket, key = uri_parts(run.input_s3_uri)
    try:
        obj = await run_in_threadpool(
            lambda: s3_from_env().get_object(Bucket=bucket, Key=key))
        source = obj["Body"].read()
    except Exception:  # noqa: BLE001
        logger.exception("rerun: could not read stored input for run %s", run_id)
        raise HTTPException(410, detail={"error": {
            "code": "file_expired",
            "message": "The stored file could not be read."}})

    filename = run.input_filename or "document.docx"
    new_id = begin_tool_run(db, user, tool=run.tool, surface=surface_of(request))

    def _progress(done: int, total: int) -> None:
        bump_progress(new_id, done=done, total=total)

    with Timer() as t:
        if run.tool == "humanize-docx":
            from orchestrator.tools.humanize_docx import humanize_docx  # noqa: PLC0415
            anchor = ((_prefs(db, user.id) or {}).get("writing_anchor") or "").strip()
            out, report = await run_in_threadpool(
                humanize_docx, source, user_anchor=anchor or None,
                on_progress=_progress)
            metrics = _humanize_metrics(report)
            units, suffix = 0, "humanized"
        else:
            from orchestrator.tools.cite_docx import cite_docx  # noqa: PLC0415
            out, report = await run_in_threadpool(cite_docx, source, add_missing=True)
            metrics = {"resolved": report.get("resolved", 0),
                       "unresolved": report.get("unresolved", 0),
                       "added": report.get("added", 0)}
            units = int(report.get("resolved") or 0) + int(report.get("unresolved") or 0)
            suffix = "cited"

    ok = out is not None and bool(report.get("ok"))
    files = await run_in_threadpool(
        store_run_files, user_id=user.id, filename=filename,
        input_bytes=source, output_bytes=out)
    charged = record_tool_run(
        db, user, surface=surface_of(request), tool=run.tool, ok=ok,
        error=None if ok else (report.get("error") or "rerun_failed"),
        units=units, usage=report.get("usage") or [], duration_ms=t.ms,
        run_id=new_id, files=files, input_filename=filename, metrics=metrics,
        parent_run_id=run.id).charged

    if not ok:
        raise HTTPException(422, detail={"error": {
            "code": report.get("error") or "rerun_failed",
            "message": report.get("detail") or "The run did not complete."}})

    stem = filename.rsplit(".", 1)[0]
    return StreamingResponse(
        io.BytesIO(out), media_type=_DOCX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{stem}-{suffix}.docx"',
            "X-Credits-Charged": str(charged),
            "X-Tool-Run-Id": str(new_id or ""),
        },
    )


@router.get("/runs/{run_id}/file/{which}")
def download_run_file(
    run_id: int, which: str,
    # GET-only (browser <a download>) — the ?st= token names this exact run AND
    # half, so a leaked URL opens one file for two minutes rather than both.
    user: User = Depends(stream_user_factory(
        lambda run_id, which: f"tool-run-file:{run_id}/{which}")),
    db: Session = Depends(db_session),
):
    """302 to a fresh 5-minute signed URL for a run's input or output .docx."""
    from ..auth_admin import readable_run  # noqa: PLC0415
    from ..tool_artifacts import FILE_RETENTION_DAYS, uri_parts  # noqa: PLC0415
    from .uploads import _DOCX_MIME  # noqa: PLC0415

    if which not in ("input", "output"):
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    run = readable_run(db, user, run_id)
    uri = run.input_s3_uri if which == "input" else run.output_s3_uri
    if not uri:
        # 410, not 404: a run whose files aged out is a different fact from a
        # run that never existed, and the student is entitled to the difference
        # rather than being told their document was never there.
        raise HTTPException(410, detail={"error": {
            "code": "file_expired",
            "message": f"Files from a tool run are kept for "
                       f"{FILE_RETENTION_DAYS} days."}})
    bucket, key = uri_parts(uri)
    if not bucket:
        raise HTTPException(500, detail={"error": {"code": "bad_s3_uri"}})
    name = run.input_filename or "document.docx"
    if which == "output":
        stem = name.rsplit(".", 1)[0]
        name = f"{stem}-{'cited' if run.tool == 'cite-docx' else 'humanized'}.docx"
    signed = s3_from_env().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key,
                "ResponseContentType": _DOCX_MIME,
                "ResponseContentDisposition": f'attachment; filename="{name}"'},
        ExpiresIn=300,
    )
    return RedirectResponse(url=signed, status_code=302)


# ---------------------------------------------------------------------------
# Document humanize — .docx in, .docx out, formatting intact
# ---------------------------------------------------------------------------

def _humanize_metrics(report: dict) -> dict:
    """Flatten a humanize_docx report into a ToolRun.metrics dict.

    The walk computes the exact reason each batch kept its original text, and
    this router used to persist only {"rewritten", "skipped"} — so a real run
    that left 4,990 words untouched had a row that could not answer "why".
    Failures are aggregated per error KIND, in PARAGRAPHS (a batch entry
    carries several) — counts, never prose, the line models.py::ToolRun draws.

    Shared by /document/humanize and /runs/{id}/rerun so the re-run of a bad
    document cannot be less debuggable than the run that made it bad.
    """
    m = {"rewritten": report.get("rewritten", 0),
         "skipped": report.get("skipped", 0)}
    if report.get("coverage") is not None:
        m["coverage"] = report["coverage"]
    # Skips the tool DECLINED to make (prose already good) recorded apart from
    # skips where the run broke — without the split, a re-uploaded document
    # that needed nothing reads identically to a run the provider dropped.
    if report.get("declined") is not None:
        m["declined"] = report["declined"]
    # Whether the student got their own file back. Without this the history
    # cannot distinguish "we rewrote little" from "we rewrote little AND handed
    # the original back", and support would have to guess which bytes the
    # download link holds.
    if report.get("reverted"):
        m["reverted"] = True
    counts: dict[str, int] = {}
    for f in report.get("failures") or []:
        kind = str(f.get("error") or "unknown")
        counts[kind] = counts.get(kind, 0) + int(f.get("paragraphs") or 0)
    if counts:
        m["failures"] = counts
    return m


class DocScanOut(BaseModel):
    ok: bool
    body_paragraphs: int = 0
    headings: int = 0
    short_or_captions: int = 0
    tables: int = 0
    passages: int = 0
    chars: int = 0
    # Whitespace-separated tokens in the eligible prose. Partners price on this
    # — it is the count a student recognises from their own word processor.
    words: int = 0
    error: str | None = None
    detail: str | None = None


async def _read_docx(file: UploadFile) -> bytes:
    """Shared validation for both document routes."""
    from .uploads import _DOCX_MIME, _max_bytes  # noqa: PLC0415

    fname = (file.filename or "").lower()
    mime = file.content_type or "application/octet-stream"
    # .docx only. A PDF has no paragraph objects to write back into, so the
    # in-place rewrite this route exists for is impossible on one — better an
    # explicit 415 than a silent fallback to the lossy text path.
    if mime != _DOCX_MIME and not fname.endswith(".docx"):
        raise HTTPException(415, detail={"error": {
            "code": "docx_only",
            "message": "Document rewriting needs a .docx — a PDF has no editable "
                       "paragraphs. Save as Word, or paste the passage instead."}})
    body = await file.read()
    if len(body) > _max_bytes():
        raise HTTPException(413, detail={"error": {
            "code": "too_large", "message": f"file exceeds {_max_bytes()} bytes"}})
    return body


@router.post("/document/scan", response_model=DocScanOut)
async def scan_document(request: Request, file: UploadFile = File(...),
                        user: User = Depends(current_user),
                        db: Session = Depends(db_session)) -> DocScanOut:
    """Report what a rewrite would touch. No LLM, no charge.

    The confirm-before-you-spend half of the flow: a thesis is hundreds of
    paragraphs, and letting one click bill an unknown amount of a student's
    credits is not a defensible default. Charging for the ESTIMATE would defeat
    the point of showing it, so this stays in pricing.TOOL_FREE — but it is
    recorded, because scan-then-abandon is the drop-off worth watching.
    """
    from orchestrator.tools.humanize_docx import scan_docx  # noqa: PLC0415

    body = await _read_docx(file)
    out = scan_docx(body)
    if not out.get("ok"):
        record_tool_run(db, user, surface=surface_of(request), tool="scan-docx", ok=False,
                        error=out.get("error") or "unreadable")
        return DocScanOut(ok=False, error=out.get("error"),
                          detail="This file could not be opened as a Word document.")
    record_tool_run(db, user, surface=surface_of(request), tool="scan-docx", units=out.get("body_paragraphs") or 0)
    return DocScanOut(**out)


@router.post("/document/humanize")
async def humanize_document(request: Request, file: UploadFile = File(...),
                            # None = read it off the document. This defaulted to
                            # "vi", which the rewrite prompt takes as an
                            # instruction, so an English thesis came back
                            # translated. A caller may still force a value.
                            language: str | None = None,
                            user: User = Depends(current_user),
                            db: Session = Depends(db_session)):
    """Rewrite the body prose and stream the .docx back, formatting intact.

    Streams like exports.export_module_docx rather than storing: the output is
    a one-shot artifact of a tool call, so an S3 object and a DB row would be
    litter attached to a project the student does not have.

    Billed on TOKENS — every passage's usage is accumulated by the walk and
    charged once here, at each model's own rate. The count lands in the
    X-Credits-Charged header because a streamed file cannot also carry a JSON
    body; it is in token_ledger and tool_runs either way.
    """
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415
    from orchestrator.tools.humanize_docx import humanize_docx  # noqa: PLC0415
    from .uploads import _DOCX_MIME  # noqa: PLC0415
    from ..tool_artifacts import store_run_files  # noqa: PLC0415
    from ..tool_billing import begin_tool_run, bump_progress  # noqa: PLC0415
    from ..user_memory import load_user_prefs as _prefs  # noqa: PLC0415

    body = await _read_docx(file)
    # Same anchor fallback as the passage route: a student who saved their
    # sample once must not be asked for it again per document.
    anchor = ((_prefs(db, user.id) or {}).get("writing_anchor") or "").strip()

    # Open the row before the walk so /tools/runs/{id}/progress has something to
    # report while this request is still open. A thesis is ~70 sequential model
    # calls; without this the student watches a spinner for minutes with no way
    # to tell a working run from a dead one.
    run_id = begin_tool_run(db, user, tool="humanize-docx",
                            surface=surface_of(request))
    def _progress(done: int, total: int) -> None:
        bump_progress(run_id, done=done, total=total)

    with Timer() as t:
        # run_in_threadpool, not a direct call: humanize_docx is SYNCHRONOUS and
        # walks the whole document — a 132-paragraph thesis is ~70 sequential
        # model calls, tens of minutes. Called inline from this `async def` it
        # occupied the event loop for that entire time, so the API served
        # nothing else (not even /auth/me) and could not shut down cleanly while
        # a rewrite was in flight. The work is I/O-bound waiting on the
        # provider, so a worker thread is the right place for it.
        out, report = await run_in_threadpool(
            humanize_docx, body, language=language, user_anchor=anchor or None,
            on_progress=_progress)
    ok = out is not None and bool(report.get("ok"))
    # Both halves kept, including on failure: the input is what makes a bad run
    # reproducible and re-runnable without asking the student for the file again.
    files = await run_in_threadpool(
        store_run_files, user_id=user.id,
        filename=file.filename or "document.docx",
        input_bytes=body, output_bytes=out)
    charged = record_tool_run(
        db, user, surface=surface_of(request), tool="humanize-docx", ok=ok,
        error=None if ok else (report.get("error") or "rewrite_failed"),
        usage=report.get("usage") or [], duration_ms=t.ms,
        run_id=run_id, files=files, input_filename=file.filename,
        # The counts the response headers carried and the history threw away:
        # a run that left half the document untouched now says so afterwards —
        # including WHY, per failure kind (see _humanize_metrics).
        metrics=_humanize_metrics(report)).charged

    if not ok:
        raise HTTPException(422, detail={"error": {
            "code": report.get("error") or "rewrite_failed",
            "message": report.get("detail")
                       or "No paragraph could be rewritten — your document was not changed."}})

    stem = (file.filename or "document.docx").rsplit(".", 1)[0]
    return StreamingResponse(
        io.BytesIO(out), media_type=_DOCX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{stem}-humanized.docx"',
            "X-Credits-Charged": str(charged),
            "X-Paragraphs-Rewritten": str(report.get("rewritten", 0)),
            "X-Paragraphs-Skipped": str(report.get("skipped", 0)),
            # The share of eligible prose actually rewritten. The headless
            # surfaces (auto-mode, partner API) read headers, not run history,
            # and rewritten/skipped alone made callers do the division that
            # nobody did — which is how 70% untouched passed unnoticed.
            "X-Rewrite-Coverage": str(report.get("coverage", "")),
            # The skip partition, carried the same way: declined = the guard
            # refusing to make already-good prose worse, which is success. A
            # 200 with X-Already-Human: 1 is "your writing already reads as
            # human; nothing to change" — a sentence neither "done" nor
            # "failed" can carry. "1"/"0" because every header here is a
            # number, not a word.
            "X-Paragraphs-Declined": str(report.get("declined", 0)),
            "X-Already-Human": "1" if report.get("already_human") else "0",
        },
    )


# ---------------------------------------------------------------------------
# Document citation — .docx in, .docx out, citations resolved and added
# ---------------------------------------------------------------------------

class CiteScanOut(BaseModel):
    ok: bool
    intext_citations: int = 0
    distinct_sources: int = 0
    existing_references: int = 0
    has_reference_section: bool = False
    body_paragraphs: int = 0
    passages: int = 0
    headings: int = 0
    tables: int = 0
    # What phase A will cost, quoted before it runs. Phase B is billed on tokens
    # and cannot be quoted from a scan, so it is deliberately not in here.
    resolve_cost: int = 0
    error: str | None = None
    detail: str | None = None


@router.post("/document/cite/scan", response_model=CiteScanOut)
async def scan_document_citations(request: Request, file: UploadFile = File(...),
                                  user: User = Depends(current_user),
                                  db: Session = Depends(db_session)) -> CiteScanOut:
    """Report what citing would touch, and what it will cost. No LLM, no charge.

    The estimate stays free (pricing.TOOL_FREE) for the same reason the humanize
    scan does: charging for the number a student needs in order to decide
    whether to pay defeats the point of showing it. "Add sources to my thesis"
    is exactly the operation nobody should agree to blind.
    """
    from orchestrator.tools.cite_docx import scan_cite_docx  # noqa: PLC0415
    from ..tool_billing import tool_cost  # noqa: PLC0415

    body = await _read_docx(file)
    out = scan_cite_docx(body)
    if not out.get("ok"):
        record_tool_run(db, user, surface=surface_of(request), tool="scan-cite-docx", ok=False,
                        error=out.get("error") or "unreadable")
        return CiteScanOut(ok=False, error=out.get("error"),
                           detail="This file could not be opened as a Word document.")
    sources = out.get("distinct_sources") or 0
    record_tool_run(db, user, surface=surface_of(request), tool="scan-cite-docx", units=sources)
    # Phase A's price, quoted before it is spent. Phase B is token-billed and
    # cannot be quoted from a scan — the UI says so rather than guessing.
    return CiteScanOut(**out, resolve_cost=tool_cost("cite-docx", units=sources))


@router.post("/document/cite")
async def cite_document(request: Request, file: UploadFile = File(...),
                        add_missing: bool = True,
                        user: User = Depends(current_user),
                        db: Session = Depends(db_session)):
    """Return the .docx with its reference list rebuilt and its gaps cited.

    Streams the file back like /document/humanize; the counts ride in headers
    because a streamed document cannot also carry a JSON body.

    `add_missing=false` runs phase A only — resolve the existing citations and
    rebuild the reference list from CrossRef records. It calls no model, so it
    is billed per SOURCE looked up rather than on tokens, and stays available as
    the half of this feature that cannot go wrong.

    Both halves are billed on one run: units for the CrossRef lookups phase A
    made, tokens for the model calls phase B made, added together.
    """
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415
    from orchestrator.tools.cite_docx import cite_docx  # noqa: PLC0415
    from .uploads import _DOCX_MIME  # noqa: PLC0415
    from ..tool_artifacts import store_run_files  # noqa: PLC0415
    from ..tool_billing import begin_tool_run, bump_progress  # noqa: PLC0415

    body = await _read_docx(file)
    run_id = begin_tool_run(db, user, tool="cite-docx", surface=surface_of(request))

    def _progress(done: int, total: int) -> None:
        bump_progress(run_id, done=done, total=total)

    with Timer() as t:
        # Off the event loop for the same reason as /document/humanize above:
        # phase A is a CrossRef round-trip per source and phase B is model
        # calls, so this blocks for minutes on a real thesis.
        out, report = await run_in_threadpool(
            cite_docx, body, add_missing=add_missing, on_progress=_progress)
    ok = out is not None and bool(report.get("ok"))
    # Billed per source ACTUALLY looked up — resolved plus unresolved, since a
    # CrossRef query was spent either way, but not the entries carried through
    # from the student's own list untouched.
    sources = int(report.get("resolved") or 0) + int(report.get("unresolved") or 0)
    files = await run_in_threadpool(
        store_run_files, user_id=user.id,
        filename=file.filename or "document.docx",
        input_bytes=body, output_bytes=out)
    charged = record_tool_run(
        db, user, surface=surface_of(request), tool="cite-docx", ok=ok,
        error=None if ok else (report.get("error") or "cite_failed"),
        units=sources, usage=report.get("usage") or [], duration_ms=t.ms,
        run_id=run_id, files=files, input_filename=file.filename,
        metrics={"resolved": report.get("resolved", 0),
                 "unresolved": report.get("unresolved", 0),
                 "added": report.get("added", 0)}).charged

    if not ok:
        raise HTTPException(422, detail={"error": {
            "code": report.get("error") or "cite_failed",
            "message": report.get("detail")
                       or "This document could not be processed — it was not changed."}})

    stem = (file.filename or "document.docx").rsplit(".", 1)[0]
    return StreamingResponse(
        io.BytesIO(out), media_type=_DOCX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{stem}-cited.docx"',
            "X-Credits-Charged": str(charged),
            "X-Citations-Resolved": str(report.get("resolved", 0)),
            "X-Citations-Unresolved": str(report.get("unresolved", 0)),
            "X-Citations-Weak": str(report.get("weak", 0)),
            "X-References-Uncited": str(report.get("orphans", 0)),
            "X-Citations-Added": str(report.get("added", 0)),
            "X-Claims-Marked": str(report.get("marked", 0)),
            "X-Citations-Linked": str(report.get("linked", 0)),
            "X-References": str(report.get("references", 0)),
        },
    )

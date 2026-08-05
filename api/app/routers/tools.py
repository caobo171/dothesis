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

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..jwt_auth import AuthedBody
from ..models import User
from ..user_memory import load_user_prefs, write_user_prefs

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


@router.post("/writing-rhythm", response_model=RhythmOut)
def writing_rhythm(body: RhythmBody, user: User = Depends(current_user)) -> RhythmOut:
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

    score = StylometricScorer().score(body.text)
    if score is None:
        return RhythmOut(
            ok=False, verdict="too_short", basis="sentence-length burstiness",
            detail="Needs at least 3 sentences to judge rhythm.")

    if score >= 0.7:
        verdict = "very_even"
    elif score >= 0.45:
        verdict = "somewhat_even"
    else:
        verdict = "varied"
    return RhythmOut(
        ok=True, score=score, verdict=verdict,
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
def verify_citation(body: CitationBody, user: User = Depends(current_user)) -> CitationOut:
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
    return _verify_one(body.reference)


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


@router.post("/verify-citations", response_model=CitationListOut)
def verify_citations(
    body: CitationListBody, user: User = Depends(current_user),
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
        return CitationListOut(
            ok=True, detected=0, checked=0,
            detail="No references found. This looks for lines carrying a year or "
                   "a DOI, usually under a 'Tài liệu tham khảo' / 'References' "
                   "heading — paste the reference list, or the whole document.")

    capped = refs[:_MAX_REFS]
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_verify_one, capped))

    items = [
        CitationItem(reference=ref, **res.model_dump())
        for ref, res in zip(capped, results, strict=True)
    ]
    return CitationListOut(
        ok=True, detected=len(refs), checked=len(items),
        truncated=len(refs) > len(capped), items=items)


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


@router.post("/plagiarism-check", response_model=SimilarityOut)
def plagiarism_check(body: SimilarityBody, user: User = Depends(current_user)) -> SimilarityOut:
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
        return SimilarityOut(
            ok=False,
            error="provider_not_configured",
            detail="No similarity provider is configured for this deployment, "
                   "so this passage was NOT checked. This is not a result of "
                   "'no matches found'.",
        )
    try:
        raw = provider.check(body.text, language=body.language)
    except Exception:  # noqa: BLE001
        logger.exception("plagiarism-check failed for user %s", user.id)
        # Never degrade a transport failure into "clean" — same rule as
        # verify_citation's network-failure branch.
        return SimilarityOut(
            ok=False, error="provider_error",
            detail="The similarity provider could not be reached, so this "
                   "passage was NOT checked.",
        )
    return SimilarityOut(
        ok=True,
        score=raw.get("score"),
        matches=[SimilarityMatch(**m) for m in (raw.get("matches") or [])],
        provider=raw.get("provider") or getattr(provider, "name", None),
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
async def extract_text(file: UploadFile = File(...),
                       user: User = Depends(current_user)) -> ExtractOut:
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
    if not text:
        # A scanned PDF is images, not text. Say which problem it is — "no text"
        # sends the student looking for a bug in our parser instead of exporting
        # a text-based copy.
        return ExtractOut(
            ok=False, filename=file.filename, error="no_text",
            detail="No text could be read from this file. If it's a scan or "
                   "photo, the pages are images — export a text-based PDF or "
                   "paste the passage instead.")
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
# Document humanize — .docx in, .docx out, formatting intact
# ---------------------------------------------------------------------------

class DocScanOut(BaseModel):
    ok: bool
    body_paragraphs: int = 0
    headings: int = 0
    short_or_captions: int = 0
    tables: int = 0
    passages: int = 0
    chars: int = 0
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
async def scan_document(file: UploadFile = File(...),
                        user: User = Depends(current_user)) -> DocScanOut:
    """Report what a rewrite would touch. No LLM, no charge.

    The confirm-before-you-spend half of the flow: a thesis is hundreds of
    paragraphs, and letting one click bill an unknown amount of a student's
    credits is not a defensible default.
    """
    from orchestrator.tools.humanize_docx import scan_docx  # noqa: PLC0415

    body = await _read_docx(file)
    out = scan_docx(body)
    if not out.get("ok"):
        return DocScanOut(ok=False, error=out.get("error"),
                          detail="This file could not be opened as a Word document.")
    return DocScanOut(**out)


@router.post("/document/humanize")
async def humanize_document(file: UploadFile = File(...),
                            language: str = "vi",
                            user: User = Depends(current_user),
                            db: Session = Depends(db_session)):
    """Rewrite the body prose and stream the .docx back, formatting intact.

    Streams like exports.export_module_docx rather than storing: the output is
    a one-shot artifact of a tool call, so an S3 object and a DB row would be
    litter attached to a project the student does not have.

    Billing reuses humanize's `_meter_and_charge` — every passage's usage is
    accumulated by the walk and charged once here, at each model's own rate.
    The count lands in the X-Credits-Charged header because a streamed file
    cannot also carry a JSON body; it is in token_ledger either way.
    """
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from orchestrator.tools.humanize_docx import humanize_docx  # noqa: PLC0415
    from .humanize import _meter_and_charge  # noqa: PLC0415
    from .uploads import _DOCX_MIME  # noqa: PLC0415
    from ..user_memory import load_user_prefs as _prefs  # noqa: PLC0415

    body = await _read_docx(file)
    # Same anchor fallback as the passage route: a student who saved their
    # sample once must not be asked for it again per document.
    anchor = ((_prefs(db, user.id) or {}).get("writing_anchor") or "").strip()

    out, report = humanize_docx(body, language=language, user_anchor=anchor or None)
    charged = _meter_and_charge(db, user, report.get("usage") or [])

    if out is None or not report.get("ok"):
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
    error: str | None = None
    detail: str | None = None


@router.post("/document/cite/scan", response_model=CiteScanOut)
async def scan_document_citations(file: UploadFile = File(...),
                                  user: User = Depends(current_user)) -> CiteScanOut:
    """Report what citing would touch. No LLM, no charge.

    Phase A (resolving the citations already in the document) is free either
    way; this exists for phase B, which spends tokens per claim. "Add sources to
    my thesis" is exactly the operation nobody should agree to blind.
    """
    from orchestrator.tools.cite_docx import scan_cite_docx  # noqa: PLC0415

    body = await _read_docx(file)
    out = scan_cite_docx(body)
    if not out.get("ok"):
        return CiteScanOut(ok=False, error=out.get("error"),
                           detail="This file could not be opened as a Word document.")
    return CiteScanOut(**out)


@router.post("/document/cite")
async def cite_document(file: UploadFile = File(...),
                        add_missing: bool = True,
                        user: User = Depends(current_user),
                        db: Session = Depends(db_session)):
    """Return the .docx with its reference list rebuilt and its gaps cited.

    Streams the file back like /document/humanize; the counts ride in headers
    because a streamed document cannot also carry a JSON body.

    `add_missing=false` runs phase A only — resolve the existing citations and
    rebuild the reference list from CrossRef records. That path calls no model
    at all and therefore charges nothing, which is worth keeping available: it
    is the half of this feature that cannot go wrong.
    """
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from orchestrator.tools.cite_docx import cite_docx  # noqa: PLC0415
    from .humanize import _meter_and_charge  # noqa: PLC0415
    from .uploads import _DOCX_MIME  # noqa: PLC0415

    body = await _read_docx(file)
    out, report = cite_docx(body, add_missing=add_missing)
    charged = _meter_and_charge(db, user, report.get("usage") or [])

    if out is None or not report.get("ok"):
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

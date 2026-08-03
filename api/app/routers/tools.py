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

import httpx
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
_CROSSREF = "https://api.crossref.org/works"


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


def _crossref_by_doi(doi: str) -> dict | None:
    r = httpx.get(f"{_CROSSREF}/{doi}", timeout=15,
                  headers={"User-Agent": "DoThesis/1.0 (citation check)"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("message")


def _crossref_by_text(text: str) -> dict | None:
    r = httpx.get(_CROSSREF, timeout=15,
                  params={"query.bibliographic": text[:400], "rows": 1},
                  headers={"User-Agent": "DoThesis/1.0 (citation check)"})
    r.raise_for_status()
    items = (r.json().get("message") or {}).get("items") or []
    return items[0] if items else None


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


@router.post("/verify-citation", response_model=CitationOut)
def verify_citation(body: CitationBody, user: User = Depends(current_user)) -> CitationOut:
    """Check a reference against CrossRef — does this actually exist?

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
    """
    ref = body.reference.strip()
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

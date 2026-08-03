"""Stateless helper tools — no project, no thesis, just text in / answer out.

These exist to be exposed through the MCP connector (mcp/server_lite.py), where
the useful shape is a single self-contained call a student can make mid-chat.
Everything project-scoped is already served by chat.py / papers.py; this module
is only for the things that need nothing but their arguments.

Both endpoints are also plain REST, so the web app can use them without going
near MCP.
"""
from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import current_user
from ..models import User

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
